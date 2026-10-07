#!/usr/bin/env python3
"""
Lab03S01 - Card A: seleção de repositórios, funil e metadados.

Fluxo:
  1. Busca candidatos em /search/repositories, fatiando por faixas de estrelas
     (a busca devolve no máximo 1.000 resultados por consulta).
  2. Embaralha os candidatos com seed fixa (amostra diversa e reproduzível).
  3. Avalia um a um, até atingir o alvo (padrão: 100):
       a) usa GitHub Actions?                      (/actions/workflows)
       b) >= 5 releases publicadas na janela?      (/releases)
       c) >= 50 workflow runs válidos na janela?   (/actions/runs)
  4. Coleta metadados (estrelas, linguagem, contribuidores, idade, default_branch).
  5. Gera funil, descartados e a lista final em CSV.

Cache em disco + retomada: toda resposta da API é salva em --cache. Se o script
for interrompido (rate limit, rede, Ctrl+C), rodar o mesmo comando continua de
onde parou, sem repetir chamadas.

Uso:
    export GITHUB_TOKEN=ghp_xxx
    python selecao_repos.py --inicio 2025-01-01 --fim 2025-12-31

Dependências: pip install requests
"""

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = "https://api.github.com"
MAX_RETRIES = 5
CONCLUSOES_VALIDAS = ("success", "failure", "timed_out", "startup_failure")
FAIXAS_PADRAO = [
    "1000..2000",
    "2000..5000",
    "5000..10000",
    "10000..25000",
    "25000..60000",
    ">60000",
]


# --------------------------------------------------------------------------
# Cliente HTTP com cache, rate limit e backoff
# (se o Card C entregar a camada de cache/rate limit, troque esta classe por ela)
# --------------------------------------------------------------------------
class GitHubClient:
    def __init__(self, token: str, cache_dir: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "lab03-dora-pipeline",
            }
        )
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.chamadas = 0
        self.cache_hits = 0

    def _arquivo_cache(self, url: str, params: dict | None) -> Path:
        bruto = url + "?" + json.dumps(params or {}, sort_keys=True)
        return self.cache_dir / (hashlib.sha256(bruto.encode()).hexdigest() + ".json")

    @staticmethod
    def _limitado(resp: requests.Response) -> bool:
        if resp.status_code not in (403, 429):
            return False
        if resp.headers.get("X-RateLimit-Remaining") == "0":
            return True
        if "Retry-After" in resp.headers:
            return True
        return "rate limit" in resp.text.lower()

    @staticmethod
    def _esperar_reset(resp: requests.Response) -> None:
        if "Retry-After" in resp.headers:
            espera = int(resp.headers["Retry-After"]) + 1
        else:
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            espera = max(reset - int(time.time()), 0) + 2
        print(f"  [rate limit] aguardando {espera}s...", flush=True)
        time.sleep(espera)

    def get(self, path: str, params: dict | None = None):
        """Retorna (status, corpo_json, link_header). Usa cache em disco."""
        url = path if path.startswith("http") else API + path
        arq = self._arquivo_cache(url, params)
        if arq.exists():
            d = json.loads(arq.read_text(encoding="utf-8"))
            self.cache_hits += 1
            return d["status"], d["body"], d["link"]

        tentativa = 0
        while True:
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                if tentativa >= MAX_RETRIES:
                    raise RuntimeError(f"Falha de rede em {url}: {exc}") from exc
                self._backoff(tentativa)
                tentativa += 1
                continue

            self.chamadas += 1

            if self._limitado(resp):
                self._esperar_reset(resp)
                continue
            if resp.status_code >= 500:
                if tentativa >= MAX_RETRIES:
                    raise RuntimeError(f"HTTP {resp.status_code} persistente em {url}")
                self._backoff(tentativa)
                tentativa += 1
                continue

            # Pausa proativa: acabou a cota desta janela, espera antes da próxima chamada
            if resp.headers.get("X-RateLimit-Remaining") == "0":
                self._esperar_reset(resp)

            corpo = resp.json() if resp.content else None
            link = resp.headers.get("Link")
            arq.write_text(
                json.dumps({"status": resp.status_code, "body": corpo, "link": link}),
                encoding="utf-8",
            )
            return resp.status_code, corpo, link

    @staticmethod
    def _backoff(tentativa: int) -> None:
        espera = 2**tentativa  # 1, 2, 4, 8, 16 s
        print(f"  [erro temporário] nova tentativa em {espera}s...", flush=True)
        time.sleep(espera)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def parse_iso(texto: str | None) -> datetime | None:
    if not texto:
        return None
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def ultima_pagina(link_header: str | None) -> int | None:
    """Número da última página a partir do header Link (rel="last")."""
    if not link_header:
        return None
    m = re.search(r'<[^>]*[?&]page=(\d+)[^>]*>;\s*rel="last"', link_header)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Etapa 1: candidatos
# --------------------------------------------------------------------------
def buscar_candidatos(client: GitHubClient, faixas: list[str], inicio: datetime) -> list[dict]:
    """Busca por faixas de estrelas. Só repositórios com push desde o início da janela
    (filtro seguro: quem tem runs de push na janela tem pushed_at >= início)."""
    vistos: dict[str, dict] = {}
    for faixa in faixas:
        q = f"stars:{faixa} pushed:>={inicio:%Y-%m-%d}"
        print(f"[busca] {q}", flush=True)
        total_faixa = 0
        for pagina in range(1, 11):  # 10 páginas x 100 = teto de 1.000
            st, corpo, _ = client.get(
                "/search/repositories",
                {"q": q, "sort": "stars", "order": "desc", "per_page": 100, "page": pagina},
            )
            if st != 200:
                print(f"  aviso: busca retornou HTTP {st} (faixa {faixa}, pág. {pagina})")
                break
            if pagina == 1 and corpo["total_count"] > 1000:
                print(
                    f"  aviso: faixa {faixa} tem {corpo['total_count']} resultados; "
                    "só os 1.000 primeiros serão vistos (refine a faixa)."
                )
            itens = corpo.get("items", [])
            for r in itens:
                vistos.setdefault(r["full_name"], r)
            total_faixa += len(itens)
            if len(itens) < 100:
                break
        print(f"  {total_faixa} resultados na faixa", flush=True)
    return list(vistos.values())


# --------------------------------------------------------------------------
# Etapa 2: filtros por repositório
# --------------------------------------------------------------------------
def usa_actions(client: GitHubClient, fn: str):
    st, corpo, _ = client.get(f"/repos/{fn}/actions/workflows", {"per_page": 1})
    if st != 200:
        return None
    return corpo.get("total_count", 0) > 0


def contar_releases(client: GitHubClient, fn: str, ini: datetime, fim: datetime):
    """Releases publicadas (draft=false, prerelease=false) com published_at na janela."""
    n = 0
    pagina = 1
    while True:
        st, corpo, _ = client.get(f"/repos/{fn}/releases", {"per_page": 100, "page": pagina})
        if st != 200:
            return None
        if not corpo:
            break
        for rel in corpo:
            if rel.get("draft") or rel.get("prerelease"):
                continue
            pub = parse_iso(rel.get("published_at"))
            if pub and ini <= pub <= fim:
                n += 1
        # A listagem vem ordenada por created_at (data do commit da tag), que pode ser
        # bem anterior ao published_at: só para quando passou da janela com folga de 90 dias.
        mais_antiga = min(parse_iso(r["created_at"]) for r in corpo)
        if len(corpo) < 100 or mais_antiga < ini - timedelta(days=90):
            break
        pagina += 1
    return n


def contar_runs_validos(client: GitHubClient, fn: str, branch: str, ini: datetime, fim: datetime):
    """Runs do default branch, event=push, na janela, com conclusion em success/failure/
    timed_out/startup_failure. Usa per_page=1 e lê o total_count (1 chamada por conclusion)."""
    intervalo = f"{ini:%Y-%m-%d}..{fim:%Y-%m-%d}"
    total = 0
    for concl in CONCLUSOES_VALIDAS:
        st, corpo, _ = client.get(
            f"/repos/{fn}/actions/runs",
            {"branch": branch, "event": "push", "status": concl, "created": intervalo, "per_page": 1},
        )
        if st == 200:
            total += corpo.get("total_count", 0)
        elif st == 422 and concl == "startup_failure":
            continue  # filtro não aceito pela API: ignora esse valor
        else:
            return None
    return total


def contar_contribuidores(client: GitHubClient, fn: str):
    """per_page=1 + anon=true: o nº da última página (header Link) é o nº de contribuidores."""
    st, corpo, link = client.get(f"/repos/{fn}/contributors", {"per_page": 1, "anon": "true"})
    if st == 204 or (st == 200 and not corpo):
        return 0
    if st != 200:
        return None  # ex.: 403 "lista grande demais"
    return ultima_pagina(link) or len(corpo)


def avaliar(client, repo: dict, ini: datetime, fim: datetime, min_rel: int, min_runs: int):
    """Retorna (linha_csv | None, motivo_descarte | None, etapa_alcancada)."""
    fn = repo["full_name"]
    branch = repo["default_branch"]

    tem_actions = usa_actions(client, fn)
    if tem_actions is None:
        return None, "erro_api_workflows", 0
    if not tem_actions:
        return None, "sem_actions", 0

    n_rel = contar_releases(client, fn, ini, fim)
    if n_rel is None:
        return None, "erro_api_releases", 1
    if n_rel < min_rel:
        return None, f"menos_de_{min_rel}_releases", 1

    n_runs = contar_runs_validos(client, fn, branch, ini, fim)
    if n_runs is None:
        return None, "erro_api_runs", 2
    if n_runs < min_runs:
        return None, f"menos_de_{min_runs}_runs_validos", 2

    criado = parse_iso(repo["created_at"])
    linha = {
        "full_name": fn,
        "url": repo["html_url"],
        "stars": repo["stargazers_count"],
        "language": repo.get("language") or "",
        "contributors": contar_contribuidores(client, fn),
        "created_at": repo["created_at"],
        "age_days": (fim - criado).days,
        "default_branch": branch,
        "releases_in_window": n_rel,
        "valid_runs_in_window": n_runs,
    }
    return linha, None, 3


# --------------------------------------------------------------------------
# Saídas
# --------------------------------------------------------------------------
def salvar_csv(caminho: Path, campos: list[str], linhas: list[dict]) -> None:
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)


def montar_funil(n_candidatos, n_avaliados, alcancou, min_rel, min_runs):
    """alcancou[i] = nº de repositórios que passaram da etapa i (0=Actions, 1=releases, 2=runs)."""
    com_actions, com_rel, com_runs = alcancou
    return [
        {"etapa": "Candidatos coletados na busca", "restantes": n_candidatos, "descartados": "", "motivo": ""},
        {
            "etapa": "Avaliados (ordem aleatória, seed fixa, até atingir o alvo)",
            "restantes": n_avaliados,
            "descartados": n_candidatos - n_avaliados,
            "motivo": "não avaliados (alvo já atingido)",
        },
        {
            "etapa": "Usam GitHub Actions",
            "restantes": com_actions,
            "descartados": n_avaliados - com_actions,
            "motivo": "sem workflows / erro de API",
        },
        {
            "etapa": f">= {min_rel} releases publicadas na janela",
            "restantes": com_rel,
            "descartados": com_actions - com_rel,
            "motivo": "releases insuficientes",
        },
        {
            "etapa": f">= {min_runs} workflow runs válidos (push, default branch)",
            "restantes": com_runs,
            "descartados": com_rel - com_runs,
            "motivo": "runs insuficientes",
        },
        {"etapa": "AMOSTRA FINAL", "restantes": com_runs, "descartados": "", "motivo": ""},
    ]


def funil_markdown(funil: list[dict]) -> str:
    linhas = ["| Etapa | Restantes | Descartados | Motivo |", "|---|---|---|---|"]
    for f in funil:
        linhas.append(f"| {f['etapa']} | {f['restantes']} | {f['descartados']} | {f['motivo']} |")
    return "\n".join(linhas)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S01 - seleção de repositórios, funil e metadados")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--alvo", type=int, default=100, help="nº de repositórios da amostra")
    ap.add_argument("--min-releases", type=int, default=5)
    ap.add_argument("--min-runs", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--faixas", nargs="+", default=FAIXAS_PADRAO, help="faixas de estrelas da busca")
    ap.add_argument("--saida", default="data", help="pasta dos CSVs de saída")
    ap.add_argument("--cache", default=".cache/github", help="pasta do cache de respostas")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Defina a variável de ambiente GITHUB_TOKEN (nunca commite o token).")

    ini = datetime.strptime(args.inicio, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    fim = datetime.strptime(args.fim, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    client = GitHubClient(token, args.cache)

    try:
        candidatos = buscar_candidatos(client, args.faixas, ini)
        random.Random(args.seed).shuffle(candidatos)
        print(f"\n{len(candidatos)} candidatos únicos. Avaliando até {args.alvo} aprovados...\n")

        selecionados, descartados = [], []
        alcancou = [0, 0, 0]
        avaliados = 0

        for repo in candidatos:
            if len(selecionados) >= args.alvo:
                break
            avaliados += 1
            linha, motivo, etapa = avaliar(client, repo, ini, fim, args.min_releases, args.min_runs)
            for i in range(etapa):  # passou das etapas 0..etapa-1
                alcancou[i] += 1
            if linha:
                selecionados.append(linha)
                status = f"OK ({len(selecionados)}/{args.alvo})"
            else:
                descartados.append({"full_name": repo["full_name"], "motivo": motivo})
                status = f"descartado: {motivo}"
            print(f"[{avaliados}] {repo['full_name']} -> {status}", flush=True)
    except KeyboardInterrupt:
        sys.exit("\nInterrompido. As respostas já feitas estão no cache: rode o mesmo comando para retomar.")

    if len(selecionados) < args.alvo:
        print(f"\naviso: só {len(selecionados)} aprovados de {args.alvo}. Amplie as faixas de estrelas.")

    funil = montar_funil(len(candidatos), avaliados, alcancou, args.min_releases, args.min_runs)

    campos = [
        "full_name", "url", "stars", "language", "contributors",
        "created_at", "age_days", "default_branch",
        "releases_in_window", "valid_runs_in_window",
    ]
    salvar_csv(saida / "repos_selecionados.csv", campos, selecionados)
    salvar_csv(saida / "descartados.csv", ["full_name", "motivo"], descartados)
    salvar_csv(saida / "funil.csv", ["etapa", "restantes", "descartados", "motivo"], funil)
    (saida / "funil.md").write_text(funil_markdown(funil) + "\n", encoding="utf-8")

    print("\n" + funil_markdown(funil))
    print(
        f"\nSalvo em {saida}/ (repos_selecionados.csv, descartados.csv, funil.csv, funil.md). "
        f"Chamadas à API: {client.chamadas} | respostas do cache: {client.cache_hits}"
    )


if __name__ == "__main__":
    main()
