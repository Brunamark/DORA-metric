#!/usr/bin/env python3
"""
Lab03S01 - Card C: workflow runs, CFR (a) e tempo de recuperação (issue #3).

Fluxo, para cada repositório de data/repos_selecionados.csv:
  1. Divide a janela em meses e lista, mês a mês, os workflow runs do default branch
     disparados por push: /actions/runs?branch=...&event=push&created=INI..FIM,
     seguindo a paginação (header Link) até o fim.
  2. Com filtros, a API devolve no máximo 1.000 runs por consulta. Se um mês chega ao
     teto, ele é dividido ao meio (por dias e, dentro de um dia, por horário) até cada
     pedaço ficar abaixo do teto. Pedaço que não dá para dividir mais e continua no teto
     é marcado como incompleto (coluna fatias_no_teto do resumo).
  3. Classifica cada run pela conclusion (ver metricas.py) e calcula, por repositório:
     CFR (a), episódios de falha por workflow, tempo de recuperação (mediana, em horas)
     e a proporção de episódios censurados.

Saídas em --saida:
  runs.csv                 um run por linha, com a classificação
  episodios.csv            episódios de falha (fechados e censurados)
  runs_fatias.csv          cada consulta feita à API (mês ou pedaço), com o total_count
  workflow_runs_repos.csv  resumo por repositório

Usa o mesmo cliente com cache/retomada de selecao_repos.py.

Uso (de dentro de src/):
    python coleta_runs.py --inicio 2025-10-01 --fim 2026-10-01
"""

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from coleta_releases import tem_proxima
from metricas import (
    Run,
    cfr_runs,
    classificar_conclusao,
    episodios_falha,
    proporcao_censurados,
    tempo_recuperacao,
)
from selecao_repos import (
    CACHE_PADRAO,
    DADOS_PADRAO,
    ErroDeToken,
    GitHubClient,
    ler_repos,
    ler_token,
    parse_iso,
    parse_janela,
    salvar_csv,
)

TETO_RESULTADOS = 1000              # máximo de runs que a API devolve por consulta filtrada
MENOR_FATIA = timedelta(hours=1)    # abaixo disso a fatia não é mais dividida

CAMPOS_RUN_API = (
    "id", "workflow_id", "name", "head_branch", "event", "status", "conclusion",
    "created_at", "run_started_at", "updated_at", "run_attempt",
)
CAMPOS_RUNS = [
    "full_name", "run_id", "workflow_id", "workflow_name", "conclusion", "classe",
    "created_at", "run_started_at", "updated_at", "run_attempt",
]
CAMPOS_EPISODIOS = [
    "full_name", "workflow_id", "run_inicio", "run_fim", "inicio", "fim",
    "n_falhas", "censurado", "duracao_horas",
]
CAMPOS_FATIAS = ["full_name", "inicio", "fim", "total_count", "dividida", "no_teto", "status"]
CAMPOS_RESUMO = [
    "full_name", "default_branch", "status_runs",
    "fatias_consultadas", "fatias_divididas", "fatias_no_teto",
    "runs_coletados", "runs_sucesso", "runs_falha", "runs_ignorados", "workflows",
    "cfr_a", "episodios", "episodios_fechados", "episodios_censurados",
    "proporcao_censurados", "workflows_falha_sem_sucesso_anterior",
    "tempo_recuperacao_mediana_horas",
]


# --------------------------------------------------------------------------
# Fatias da janela
# --------------------------------------------------------------------------
def _inicio_do_dia(d: date) -> datetime:
    return datetime.combine(d, time(0, 0, 0), tzinfo=timezone.utc)


def _fim_do_dia(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def fatias_mensais(ini: datetime, fim: datetime) -> list[tuple[datetime, datetime]]:
    """Meses do calendário dentro da janela, sem sobreposição: (início, fim), ambos inclusivos.
    O primeiro e o último pedaço são cortados nas bordas da janela."""
    fatias = []
    atual = ini
    while atual <= fim:
        prox_mes = date(atual.year + atual.month // 12, atual.month % 12 + 1, 1)
        fim_fatia = min(_fim_do_dia(prox_mes - timedelta(days=1)), fim)
        fatias.append((atual, fim_fatia))
        atual = _inicio_do_dia(prox_mes)
    return fatias


def formatar_created(inicio: datetime, fim: datetime) -> str:
    """Valor do filtro created: datas quando a fatia cobre dias inteiros, senão data e hora."""
    if inicio.time() == time(0, 0, 0) and fim.time() == time(23, 59, 59):
        return f"{inicio:%Y-%m-%d}..{fim:%Y-%m-%d}"
    return f"{inicio:%Y-%m-%dT%H:%M:%SZ}..{fim:%Y-%m-%dT%H:%M:%SZ}"


def dividir_fatia(inicio: datetime, fim: datetime):
    """Divide a fatia ao meio: por dias se ela tiver 2 ou mais dias, senão por horário.
    Retorna None se a fatia já for menor que MENOR_FATIA."""
    n_dias = (fim.date() - inicio.date()).days + 1
    if n_dias >= 2:
        meio = inicio.date() + timedelta(days=n_dias // 2)
        return (inicio, _fim_do_dia(meio - timedelta(days=1))), (_inicio_do_dia(meio), fim)
    if fim - inicio < MENOR_FATIA:
        return None
    meio = inicio + (fim - inicio) / 2
    meio = meio.replace(microsecond=0)
    return (inicio, meio), (meio + timedelta(seconds=1), fim)


# --------------------------------------------------------------------------
# Coleta
# --------------------------------------------------------------------------
def _enxugar_runs(corpo: dict) -> dict:
    """Guarda só os campos usados (a resposta completa tem ~6 KB por run)."""
    return {
        "total_count": corpo.get("total_count"),
        "workflow_runs": [
            {campo: r.get(campo) for campo in CAMPOS_RUN_API}
            for r in corpo.get("workflow_runs", [])
        ],
    }


def _paginas_da_fatia(client, fn: str, branch: str, created: str):
    """Todas as páginas de uma fatia. Retorna (status_http, total_count, runs)."""
    runs, total, pagina = [], None, 1
    while True:
        st, corpo, link = client.get(
            f"/repos/{fn}/actions/runs",
            {"branch": branch, "event": "push", "created": created, "per_page": 100, "page": pagina},
            enxugar=_enxugar_runs,
        )
        if st != 200:
            return st, total, runs
        if total is None:
            total = corpo.get("total_count") or 0
        runs.extend(corpo.get("workflow_runs", []))
        # Depois da 10ª página a API recusa a consulta (teto de 1.000): não pede além dela
        if not tem_proxima(link) or pagina * 100 >= TETO_RESULTADOS:
            return 200, total, runs
        pagina += 1


def _consultar_fatia(client, fn, branch, inicio, fim, registro) -> tuple[int, list[dict]]:
    """Coleta uma fatia; se ela atingir o teto, divide e coleta as metades."""
    created = formatar_created(inicio, fim)
    st, corpo, _ = client.get(
        f"/repos/{fn}/actions/runs",
        {"branch": branch, "event": "push", "created": created, "per_page": 100, "page": 1},
        enxugar=_enxugar_runs,
    )
    linha = {
        "full_name": fn, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "total_count": "", "dividida": False, "no_teto": False, "status": "ok",
    }
    registro.append(linha)
    if st != 200:
        linha["status"] = f"erro_http_{st}"
        return st, []

    total = corpo.get("total_count") or 0
    linha["total_count"] = total
    if total >= TETO_RESULTADOS:
        metades = dividir_fatia(inicio, fim)
        if metades:
            linha["dividida"] = True
            runs, recusada = [], False
            for a, b in metades:
                st, parte = _consultar_fatia(client, fn, branch, a, b, registro)
                if st == 422:          # API recusou o filtro com horário: fica com a fatia inteira
                    recusada = True
                    break
                if st != 200:
                    return st, []
                runs.extend(parte)
            if not recusada:
                return 200, runs
            linha["dividida"] = False
        linha["no_teto"] = True   # não dá para dividir mais: a fatia fica incompleta

    st, _, runs = _paginas_da_fatia(client, fn, branch, created)
    if st != 200:
        linha["status"] = f"erro_http_{st}"
        return st, []
    return 200, runs


def coletar_runs(client, fn: str, branch: str, ini: datetime, fim: datetime):
    """Runs de push do default branch dentro da janela, sem duplicatas.
    Retorna (status_http, runs, registro_das_fatias)."""
    registro, por_id = [], {}
    for inicio, fim_fatia in fatias_mensais(ini, fim):
        st, runs = _consultar_fatia(client, fn, branch, inicio, fim_fatia, registro)
        if st != 200:
            return st, [], registro
        for r in runs:
            criado = parse_iso(r.get("created_at"))
            # Filtro defensivo: a API já filtra, mas um run fora do critério não pode entrar
            if r.get("head_branch") != branch or r.get("event") != "push":
                continue
            if criado is None or not ini <= criado <= fim:
                continue
            por_id[r["id"]] = r
    runs = sorted(por_id.values(), key=lambda r: (r["created_at"], r["id"]))
    return 200, runs, registro


def run_da_api(r: dict) -> Run:
    return Run(
        id=r["id"],
        workflow_id=r["workflow_id"],
        conclusao=r.get("conclusion"),
        criado_em=parse_iso(r["created_at"]),
        iniciado_em=parse_iso(r.get("run_started_at")),
        atualizado_em=parse_iso(r.get("updated_at")) or parse_iso(r["created_at"]),
    )


# --------------------------------------------------------------------------
# Processamento de um repositório
# --------------------------------------------------------------------------
def _resumo_vazio(fn: str, branch: str) -> dict:
    resumo = {campo: 0 for campo in CAMPOS_RESUMO}
    resumo.update({
        "full_name": fn, "default_branch": branch, "status_runs": "ok",
        "cfr_a": "", "proporcao_censurados": "", "tempo_recuperacao_mediana_horas": "",
    })
    return resumo


def _arredondar(valor, casas=4):
    return "" if valor is None else round(valor, casas)


def processar_repo(client, fn: str, branch: str, ini: datetime, fim: datetime) -> dict:
    """Retorna {"runs": [...], "episodios": [...], "fatias": [...], "resumo": {...}}.
    Todo repositório gera uma linha de resumo, mesmo quando a API falha."""
    resumo = _resumo_vazio(fn, branch)
    st, runs_api, fatias = coletar_runs(client, fn, branch, ini, fim)
    resultado = {"runs": [], "episodios": [], "fatias": fatias, "resumo": resumo}
    resumo["fatias_consultadas"] = len(fatias)
    resumo["fatias_divididas"] = sum(f["dividida"] for f in fatias)
    resumo["fatias_no_teto"] = sum(f["no_teto"] for f in fatias)
    if st != 200:
        resumo["status_runs"] = f"erro_http_{st}"
        return resultado

    runs = [run_da_api(r) for r in runs_api]
    for r, bruto in zip(runs, runs_api):
        classe = classificar_conclusao(r.conclusao) or "ignorado"
        resumo[{"sucesso": "runs_sucesso", "falha": "runs_falha", "ignorado": "runs_ignorados"}[classe]] += 1
        resultado["runs"].append({
            "full_name": fn,
            "run_id": r.id,
            "workflow_id": r.workflow_id,
            "workflow_name": bruto.get("name") or "",
            "conclusion": r.conclusao or "",
            "classe": classe,
            "created_at": bruto.get("created_at") or "",
            "run_started_at": bruto.get("run_started_at") or "",
            "updated_at": bruto.get("updated_at") or "",
            "run_attempt": bruto.get("run_attempt") or "",
        })

    episodios, sem_sucesso_anterior = episodios_falha(runs)
    for e in episodios:
        resultado["episodios"].append({
            "full_name": fn,
            "workflow_id": e.workflow_id,
            "run_inicio": e.run_inicio,
            "run_fim": "" if e.run_fim is None else e.run_fim,
            "inicio": e.inicio.isoformat(),
            "fim": "" if e.fim is None else e.fim.isoformat(),
            "n_falhas": e.n_falhas,
            "censurado": e.censurado,
            "duracao_horas": _arredondar(e.duracao_horas),
        })

    resumo["runs_coletados"] = len(runs)
    resumo["workflows"] = len({r.workflow_id for r in runs})
    resumo["cfr_a"] = _arredondar(cfr_runs(runs), 6)
    resumo["episodios"] = len(episodios)
    resumo["episodios_censurados"] = sum(e.censurado for e in episodios)
    resumo["episodios_fechados"] = len(episodios) - resumo["episodios_censurados"]
    resumo["proporcao_censurados"] = _arredondar(proporcao_censurados(episodios), 6)
    resumo["workflows_falha_sem_sucesso_anterior"] = sem_sucesso_anterior
    resumo["tempo_recuperacao_mediana_horas"] = _arredondar(tempo_recuperacao(episodios))
    return resultado


# --------------------------------------------------------------------------
# Etapa do pipeline
# --------------------------------------------------------------------------
def executar(client, ini: datetime, fim: datetime, repos: list[dict], saida: Path) -> list[dict]:
    """Coleta os runs de todos os repositórios e grava os CSVs. Retorna os resumos."""
    saida.mkdir(parents=True, exist_ok=True)
    todos_runs, todos_episodios, todas_fatias, resumos = [], [], [], []
    for i, repo in enumerate(repos, 1):
        fn, branch = repo["full_name"], repo["default_branch"]
        resultado = processar_repo(client, fn, branch, ini, fim)
        todos_runs.extend(resultado["runs"])
        todos_episodios.extend(resultado["episodios"])
        todas_fatias.extend(resultado["fatias"])
        r = resultado["resumo"]
        resumos.append(r)
        problemas = [f"status_runs={r['status_runs']}"] if r["status_runs"] != "ok" else []
        if r["fatias_no_teto"]:
            problemas.append(f"fatias_no_teto={r['fatias_no_teto']} (contagem incompleta)")
        print(
            f"[{i}/{len(repos)}] {fn} -> {r['runs_coletados']} runs, CFR(a)={r['cfr_a']}, "
            f"{r['episodios']} episódios ({r['episodios_censurados']} censurados)"
            + (f" | {', '.join(problemas)}" if problemas else ""),
            flush=True,
        )

    salvar_csv(saida / "runs.csv", CAMPOS_RUNS, todos_runs)
    salvar_csv(saida / "episodios.csv", CAMPOS_EPISODIOS, todos_episodios)
    salvar_csv(saida / "runs_fatias.csv", CAMPOS_FATIAS, todas_fatias)
    salvar_csv(saida / "workflow_runs_repos.csv", CAMPOS_RESUMO, resumos)

    print(
        f"\n{len(resumos)} repositórios processados "
        f"({sum(r['status_runs'] != 'ok' for r in resumos)} com erro de API). "
        f"Fatias divididas por atingir o teto: {sum(r['fatias_divididas'] for r in resumos)} | "
        f"fatias que continuaram no teto: {sum(r['fatias_no_teto'] for r in resumos)}.\n"
        f"Salvo em {saida}/ (runs.csv, episodios.csv, runs_fatias.csv, workflow_runs_repos.csv). "
        f"Chamadas à API: {client.chamadas} | respostas do cache: {client.cache_hits}"
    )
    return resumos


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S01 - workflow runs, CFR (a) e tempo de recuperação")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--repos", default=str(DADOS_PADRAO / "repos_selecionados.csv"),
                    help="CSV com as colunas full_name e default_branch")
    ap.add_argument("--saida", default=str(DADOS_PADRAO), help="pasta dos CSVs de saída")
    ap.add_argument("--cache", default=str(CACHE_PADRAO), help="pasta do cache de respostas")
    args = ap.parse_args()

    ini, fim = parse_janela(args.inicio, args.fim)
    client = GitHubClient(ler_token(), args.cache)
    try:
        executar(client, ini, fim, ler_repos(args.repos), Path(args.saida))
    except ErroDeToken as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        sys.exit("\nInterrompido. As respostas já feitas estão no cache: rode o mesmo comando para retomar.")


if __name__ == "__main__":
    main()
