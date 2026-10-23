#!/usr/bin/env python3
"""
Lab03S02 - releases corretivas e CFR (b) (issue #10).

Para cada repositório de data/repos_selecionados.csv:
  1. Lista as releases publicadas (draft = false, prerelease = false), com folga de um ano
     antes da janela, para achar a predecessora de cada release mesmo em linhas que
     publicam pouco (ex.: uma LTS antiga).
  2. Para cada release R da janela e cada pareamento (ver metricas.predecessoras):
     acha a predecessora P, busca os commits de P...R (/compare) e descreve R: tipo de
     mudança de versão, nº de commits, de merges, de títulos com fix/hotfix/revert e de
     atualizações de dependência. Aplica todos os critérios de release corretiva.
  3. Calcula o CFR (b) de cada combinação pareamento × critério.

Coleta eficiente:
  - No pareamento cronológico, o par (P, R) é o mesmo do lead time: as chamadas saem do
    cache (mesma chave, inclusive a versão compare-v2-mensagem).
  - Só os pares da variante "linha" que diferem do cronológico geram chamadas novas, e
    cada compare novo baixa no máximo --max-paginas páginas (100 commits cada). Uma
    comparação truncada fica marcada (`commits_truncados`).
  - O nome e as notas da release vêm da listagem que já está no cache.

Resiliência: um erro inesperado num repositório vira status no CSV e a coleta segue;
token inválido (HTTP 401) e Ctrl+C interrompem, e o cache permite retomar.

ATENÇÃO (rotulagem cega, issue #10): esta etapa NÃO faz parte do comando padrão do
pipeline. Quem rotula a amostra-ouro não deve ver a saída dela antes de commitar os
próprios rótulos. Rode com: python src/pipeline.py ... --etapas corretivas

Saídas em --saida:
  releases_corretivas.csv  uma linha por release da janela × pareamento
  cfr_entrega_repos.csv    uma linha por repositório × pareamento × critério
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from coleta_releases import commits_entre, listar_releases, publicada
from metricas import (
    CRITERIO_PADRAO,
    CRITERIOS,
    PAREAMENTOS,
    ReleaseClassificada,
    ReleasePublicada,
    avaliar_criterio,
    caracteristicas_commits,
    cfr_entrega,
    parse_versao,
    patches_recentes,
    predecessoras,
    situacao_releases,
    tem_palavra_corretiva,
    tipo_mudanca,
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

FOLGA_LISTAGEM = timedelta(days=365)
MAX_PAGINAS_PADRAO = 10          # 1.000 commits: release maior que isso não é um patch de correção
TAMANHO_NOTAS = 5000             # caracteres das notas da release analisados

CAMPOS_RELEASES = [
    "full_name", "tag_name", "published_at", "pareamento", "predecessora", "tipo_mudanca",
    "status_compare", "n_commits", "total_commits_api", "commits_truncados",
    "n_merges", "n_fix", "n_fix_amplo", "n_fix_deps", "notas_mencionam_correcao", "patch_recente_7d",
] + [f"corretiva_{c}" for c in CRITERIOS] + ["situacao_cfr"]
CAMPOS_RESUMO = [
    "full_name", "status", "pareamento", "criterio", "cfr_b", "releases_avaliadas",
    "releases_falharam", "releases_censuradas", "releases_corretivas", "releases_indeterminadas",
    "compares_404", "compares_erro", "compares_truncados",
]


def _texto_booleano(valor):
    return "" if valor is None else ("sim" if valor else "nao")


def _notas_mencionam_correcao(release: dict) -> bool:
    texto = f"{release.get('name') or ''}\n{(release.get('body') or '')[:TAMANHO_NOTAS]}"
    return any(tem_palavra_corretiva(linha, ampla=True) for linha in texto.splitlines())


# --------------------------------------------------------------------------
# Processamento de um repositório
# --------------------------------------------------------------------------
def processar_repo(client, fn: str, ini: datetime, fim: datetime,
                   max_paginas: int = MAX_PAGINAS_PADRAO) -> dict:
    """Retorna {"releases": [...], "resumo": [...]}. Erros da API ficam registrados."""
    resultado = {"releases": [], "resumo": []}
    st, brutas = listar_releases(client, fn, ini, folga=FOLGA_LISTAGEM)
    if st != 200:
        resultado["resumo"].append({**_resumo_vazio(fn), "status": f"erro_http_{st}"})
        return resultado

    por_tag = {r["tag_name"]: r for r in brutas if publicada(r)}
    lista = [ReleasePublicada(t, parse_iso(r["published_at"])) for t, r in por_tag.items()]
    na_janela = [r for r in lista if ini <= r.publicada_em <= fim]
    patch_recente = patches_recentes(na_janela)   # regra do relatório: só releases da janela, sem pareamento
    commits_do_par = {}   # (base, head) -> (status, títulos, total_api) — cada par buscado uma vez

    for pareamento in PAREAMENTOS:
        pred = predecessoras(lista, pareamento)
        linhas, classificadas = {}, {c: [] for c in CRITERIOS}
        contagem = {"compares_404": 0, "compares_erro": 0, "compares_truncados": 0}
        for r in sorted(na_janela, key=lambda x: x.publicada_em):
            base = pred[r.tag]
            linha = _descrever(client, fn, r, base, por_tag[r.tag], commits_do_par, max_paginas, contagem,
                               {"patch_recente_7d": patch_recente[r.tag]})
            linha["pareamento"] = pareamento
            linhas[r.tag] = linha
        # Releases fora da janela entram como contexto (predecessoras), nunca como corretivas avaliadas
        for criterio in CRITERIOS:
            for r in lista:
                corretiva = None
                if r.tag in linhas:
                    corretiva = linhas[r.tag][f"_corretiva_{criterio}"]
                classificadas[criterio].append(ReleaseClassificada(r.tag, r.publicada_em, pred[r.tag], corretiva))
            res = cfr_entrega(classificadas[criterio], fim, inicio_janela=ini)
            valores = [linhas[t][f"_corretiva_{criterio}"] for t in linhas]
            resultado["resumo"].append({
                "full_name": fn, "status": "ok", "pareamento": pareamento, "criterio": criterio,
                "cfr_b": "" if res.cfr is None else round(res.cfr, 6),
                "releases_avaliadas": res.n_avaliadas, "releases_falharam": res.n_falhas,
                "releases_censuradas": res.n_censuradas,
                "releases_corretivas": sum(v is True for v in valores),
                "releases_indeterminadas": sum(v is None for v in valores),
                **contagem,
            })
        situacao = situacao_releases(classificadas[CRITERIO_PADRAO], fim, inicio_janela=ini)
        for tag, linha in linhas.items():
            linha["situacao_cfr"] = situacao.get(tag, "")
            for criterio in CRITERIOS:
                linha[f"corretiva_{criterio}"] = _texto_booleano(linha.pop(f"_corretiva_{criterio}"))
            resultado["releases"].append(linha)
    return resultado


def _descrever(client, fn, r: ReleasePublicada, base, bruta, commits_do_par, max_paginas, contagem,
               extras=None) -> dict:
    """Linha de releases_corretivas.csv para a release r com predecessora `base`."""
    linha = {
        "full_name": fn, "tag_name": r.tag, "published_at": bruta["published_at"],
        "predecessora": base or "", "tipo_mudanca": "", "status_compare": "", "n_commits": "",
        "total_commits_api": "", "commits_truncados": "", "n_merges": "", "n_fix": "",
        "n_fix_amplo": "", "n_fix_deps": "",
        "notas_mencionam_correcao": _texto_booleano(_notas_mencionam_correcao(bruta)),
        "patch_recente_7d": _texto_booleano((extras or {}).get("patch_recente_7d")),
    }
    if base is None:   # primeira release da linha/história: não corrige nada
        linha["status_compare"] = "sem_predecessora"
        for criterio in CRITERIOS:   # a regra do relatório não usa a predecessora
            linha[f"_corretiva_{criterio}"] = (
                bool((extras or {}).get("patch_recente_7d")) if criterio == "relatorio_patch_7d" else False)
        return linha

    tipo = tipo_mudanca(parse_versao(base), parse_versao(r.tag))
    linha["tipo_mudanca"] = tipo or ""
    if (base, r.tag) not in commits_do_par:
        st, commits, total = commits_entre(client, fn, base, r.tag, max_paginas=max_paginas)
        commits_do_par[(base, r.tag)] = (st, [c["commit"].get("message", "") for c in commits], total)
    st, titulos, total = commits_do_par[(base, r.tag)]

    carac = None
    if st == 200:
        carac = caracteristicas_commits(titulos)
        truncado = total is not None and len(titulos) < total
        contagem["compares_truncados"] += truncado
        linha.update({
            "status_compare": "ok", "n_commits": carac.n_commits,
            "total_commits_api": "" if total is None else total,
            "commits_truncados": _texto_booleano(truncado),
            "n_merges": carac.n_merges, "n_fix": carac.n_fix,
            "n_fix_amplo": carac.n_fix_amplo, "n_fix_deps": carac.n_fix_deps,
        })
    elif st == 404:
        linha["status_compare"] = "tag_404"
        contagem["compares_404"] += 1
    else:
        linha["status_compare"] = f"erro_http_{st}"
        contagem["compares_erro"] += 1
    for criterio in CRITERIOS:
        linha[f"_corretiva_{criterio}"] = avaliar_criterio(tipo, carac, criterio, extras)
    return linha


def _resumo_vazio(fn: str) -> dict:
    resumo = {campo: "" for campo in CAMPOS_RESUMO}
    resumo["full_name"] = fn
    return resumo


# --------------------------------------------------------------------------
# Etapa do pipeline
# --------------------------------------------------------------------------
def executar(client, ini: datetime, fim: datetime, repos: list[dict], saida: Path,
             max_paginas: int = MAX_PAGINAS_PADRAO) -> list[dict]:
    """Processa todos os repositórios e grava os CSVs. Retorna as linhas de resumo."""
    saida.mkdir(parents=True, exist_ok=True)
    todas_releases, resumos = [], []
    for i, repo in enumerate(repos, 1):
        fn = repo["full_name"]
        chamadas_antes = client.chamadas
        try:
            resultado = processar_repo(client, fn, ini, fim, max_paginas)
        except (ErroDeToken, KeyboardInterrupt):
            raise
        except Exception as exc:  # um repositório problemático não derruba a coleta
            resultado = {"releases": [], "resumo": [{**_resumo_vazio(fn), "status": f"erro: {exc}"[:300]}]}
        todas_releases.extend(resultado["releases"])
        resumos.extend(resultado["resumo"])
        principal = next((r for r in resultado["resumo"] if r["pareamento"] in ("", "linha")
                          and r["criterio"] in ("", CRITERIO_PADRAO)), resultado["resumo"][0])
        print(
            f"[{i}/{len(repos)}] {fn} -> status={principal['status']} CFR(b)={principal['cfr_b']} "
            f"({principal['releases_falharam']}/{principal['releases_avaliadas']}, "
            f"{principal['releases_censuradas']} censuradas) | chamadas novas: {client.chamadas - chamadas_antes}",
            flush=True,
        )

    salvar_csv(saida / "releases_corretivas.csv", CAMPOS_RELEASES, todas_releases)
    salvar_csv(saida / "cfr_entrega_repos.csv", CAMPOS_RESUMO, resumos)
    print(
        f"\nSalvo em {saida}/ (releases_corretivas.csv, cfr_entrega_repos.csv). "
        f"Chamadas à API: {client.chamadas} | respostas do cache: {client.cache_hits}"
    )
    return resumos


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - releases corretivas e CFR (b)")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--repos", default=str(DADOS_PADRAO / "repos_selecionados.csv"), help="CSV com a coluna full_name")
    ap.add_argument("--saida", default=str(DADOS_PADRAO), help="pasta dos CSVs de saída")
    ap.add_argument("--cache", default=str(CACHE_PADRAO), help="pasta do cache de respostas")
    ap.add_argument("--max-paginas", type=int, default=MAX_PAGINAS_PADRAO,
                    help="páginas de 100 commits por compare novo (padrão: 10)")
    args = ap.parse_args()

    ini, fim = parse_janela(args.inicio, args.fim)
    client = GitHubClient(ler_token(), args.cache)
    try:
        executar(client, ini, fim, ler_repos(args.repos), Path(args.saida), args.max_paginas)
    except ErroDeToken as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        sys.exit("\nInterrompido. As respostas já feitas estão no cache: rode o mesmo comando para retomar.")


if __name__ == "__main__":
    main()
