#!/usr/bin/env python3
"""
Lab03S01 - Card B: releases, commits entre releases e lead time (issue #2).

Fluxo, para cada repositório de data/repos_selecionados.csv:
  1. Lista as releases (/releases) e as tags (/tags).
  2. Considera deploy toda release publicada (draft = false, prerelease = false).
     Ordena por published_at e forma pares consecutivos (anterior, atual).
     A primeira release do histórico não tem anterior e é ignorada.
  3. Para cada release publicada dentro da janela, busca os commits entre a anterior
     e ela em /compare/{anterior}...{atual}, seguindo a paginação (header Link) até o fim.
     Tag inexistente ou reescrita (HTTP 404): a release é pulada e contada.
  4. Calcula o lead time nas duas variantes (ver metricas.py), pela data de autoria.

Saídas em --saida:
  releases.csv          todas as releases listadas, com o status de cada uma no cálculo
  commits_releases.csv  commits entregues por release, com o lead time de cada um
  tags.csv              tags de cada repositório (variante da RQ 07)
  lead_time_repos.csv   resumo por repositório (medianas das duas variantes)

Usa o mesmo cliente com cache/retomada de selecao_repos.py.

Uso:
    export GITHUB_TOKEN=ghp_xxx
    python coleta_releases.py --inicio 2025-10-01 --fim 2026-10-01
"""

import argparse
import csv
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from metricas import (
    lead_time_commit,
    lead_time_release,
    mediana_lead_time_commit,
    mediana_lead_time_release,
)
from selecao_repos import GitHubClient, parse_iso, salvar_csv

# A listagem de releases vem ordenada por created_at (data do commit da tag), que pode
# ser bem anterior ao published_at: só paramos de paginar com essa folga.
FOLGA_PAGINACAO = timedelta(days=90)

CAMPOS_RELEASES = [
    "full_name", "tag_name", "draft", "prerelease", "published_at",
    "na_janela", "tag_anterior", "status", "n_commits", "lead_time_release_dias",
]
CAMPOS_COMMITS = ["full_name", "tag_name", "sha", "author_date", "lead_time_dias"]
CAMPOS_TAGS = ["full_name", "tag_name", "sha"]
CAMPOS_RESUMO = [
    "full_name", "releases_na_janela", "releases_calculadas", "releases_sem_commits",
    "releases_404", "releases_erro", "commits",
    "lead_time_release_mediana_dias", "lead_time_commit_mediana_dias",
]


def tem_proxima(link_header: str | None) -> bool:
    return bool(link_header and re.search(r'rel="next"', link_header))


def publicada(release: dict) -> bool:
    return not release.get("draft") and not release.get("prerelease") and bool(release.get("published_at"))


# --------------------------------------------------------------------------
# Coleta
# --------------------------------------------------------------------------
def listar_releases(client, fn: str, ini: datetime) -> list[dict] | None:
    """Releases do repositório, até achar uma publicada antes da janela (a anterior
    da primeira release da janela). None em erro de API."""
    releases = []
    pagina = 1
    while True:
        st, corpo, link = client.get(f"/repos/{fn}/releases", {"per_page": 100, "page": pagina})
        if st != 200:
            return None
        if not corpo:
            break
        releases.extend(corpo)
        achou_anterior = any(publicada(r) and parse_iso(r["published_at"]) < ini for r in releases)
        mais_antiga = min(parse_iso(r["created_at"]) for r in corpo)
        if not tem_proxima(link) or (achou_anterior and mais_antiga < ini - FOLGA_PAGINACAO):
            break
        pagina += 1
    return releases


def listar_tags(client, fn: str) -> list[dict] | None:
    tags = []
    pagina = 1
    while True:
        st, corpo, link = client.get(f"/repos/{fn}/tags", {"per_page": 100, "page": pagina})
        if st != 200:
            return None
        tags.extend(corpo or [])
        if not tem_proxima(link):
            return tags
        pagina += 1


def _enxugar_compare(corpo: dict) -> dict:
    """Guarda só o necessário do /compare (sem os diffs dos arquivos)."""
    return {
        "total_commits": corpo.get("total_commits"),
        "commits": [
            {"sha": c["sha"], "commit": {"author": {"date": c["commit"]["author"]["date"]}}}
            for c in corpo.get("commits", [])
        ],
    }


def commits_entre(client, fn: str, base: str, head: str) -> tuple[int, list[dict]]:
    """Commits em head que não estão em base. Retorna (status_http, commits);
    status diferente de 200 significa que a comparação falhou (ex.: 404)."""
    caminho = f"/repos/{fn}/compare/{quote(base, safe='')}...{quote(head, safe='')}"
    commits = []
    pagina = 1
    while True:
        st, corpo, link = client.get(caminho, {"per_page": 100, "page": pagina}, enxugar=_enxugar_compare)
        if st != 200:
            return st, []
        commits.extend(corpo.get("commits", []))
        if not tem_proxima(link):
            break
        pagina += 1
    total = corpo.get("total_commits")
    if total is not None and total != len(commits):
        print(f"  aviso: {fn} {base}...{head}: {len(commits)} de {total} commits", flush=True)
    return 200, commits


# --------------------------------------------------------------------------
# Processamento de um repositório
# --------------------------------------------------------------------------
def processar_repo(client, fn: str, ini: datetime, fim: datetime) -> dict | None:
    """Retorna {"releases": [...], "commits": [...], "resumo": {...}} ou None em erro de API."""
    releases = listar_releases(client, fn, ini)
    if releases is None:
        return None

    publicadas = sorted((r for r in releases if publicada(r)), key=lambda r: parse_iso(r["published_at"]))
    anterior_de = {id(r): publicadas[i - 1] if i > 0 else None for i, r in enumerate(publicadas)}

    linhas_rel, linhas_commits, para_medianas = [], [], []
    contagem = {"na_janela": 0, "calculadas": 0, "sem_commits": 0, "404": 0, "erro": 0}

    for r in releases:
        pub = parse_iso(r.get("published_at"))
        na_janela = publicada(r) and ini <= pub <= fim
        linha = {
            "full_name": fn,
            "tag_name": r["tag_name"],
            "draft": r.get("draft", False),
            "prerelease": r.get("prerelease", False),
            "published_at": r.get("published_at") or "",
            "na_janela": na_janela,
            "tag_anterior": "",
            "status": "",
            "n_commits": "",
            "lead_time_release_dias": "",
        }
        linhas_rel.append(linha)

        if r.get("draft"):
            linha["status"] = "excluida_draft"
            continue
        if r.get("prerelease"):
            linha["status"] = "excluida_prerelease"
            continue
        if not na_janela:
            linha["status"] = "fora_da_janela"
            continue

        contagem["na_janela"] += 1
        anterior = anterior_de[id(r)]
        if anterior is None:
            linha["status"] = "primeira_release"
            continue
        linha["tag_anterior"] = anterior["tag_name"]

        st, commits = commits_entre(client, fn, anterior["tag_name"], r["tag_name"])
        if st == 404:
            linha["status"] = "tag_404"
            contagem["404"] += 1
            continue
        if st != 200:
            linha["status"] = f"erro_http_{st}"
            contagem["erro"] += 1
            continue

        datas = [parse_iso(c["commit"]["author"]["date"]) for c in commits]
        linha["n_commits"] = len(datas)
        if not datas:
            linha["status"] = "sem_commits"
            contagem["sem_commits"] += 1
            continue

        linha["status"] = "ok"
        linha["lead_time_release_dias"] = round(lead_time_release(pub, datas), 4)
        contagem["calculadas"] += 1
        para_medianas.append((pub, datas))
        for c, lt in zip(commits, lead_time_commit(pub, datas)):
            linhas_commits.append({
                "full_name": fn,
                "tag_name": r["tag_name"],
                "sha": c["sha"],
                "author_date": c["commit"]["author"]["date"],
                "lead_time_dias": round(lt, 4),
            })

    med_rel = mediana_lead_time_release(para_medianas)
    med_commit = mediana_lead_time_commit(para_medianas)
    resumo = {
        "full_name": fn,
        "releases_na_janela": contagem["na_janela"],
        "releases_calculadas": contagem["calculadas"],
        "releases_sem_commits": contagem["sem_commits"],
        "releases_404": contagem["404"],
        "releases_erro": contagem["erro"],
        "commits": len(linhas_commits),
        "lead_time_release_mediana_dias": "" if med_rel is None else round(med_rel, 4),
        "lead_time_commit_mediana_dias": "" if med_commit is None else round(med_commit, 4),
    }
    return {"releases": linhas_rel, "commits": linhas_commits, "resumo": resumo}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S01 - releases, commits entre releases e lead time")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--repos", default="data/repos_selecionados.csv", help="CSV com a coluna full_name")
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
    with open(args.repos, newline="", encoding="utf-8") as f:
        repos = [linha["full_name"] for linha in csv.DictReader(f)]

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    client = GitHubClient(token, args.cache)

    todas_releases, todos_commits, todas_tags, resumos = [], [], [], []
    try:
        for i, fn in enumerate(repos, 1):
            resultado = processar_repo(client, fn, ini, fim)
            if resultado is None:
                print(f"[{i}/{len(repos)}] {fn} -> erro ao listar releases", flush=True)
                continue
            tags = listar_tags(client, fn) or []
            todas_releases.extend(resultado["releases"])
            todos_commits.extend(resultado["commits"])
            todas_tags.extend({"full_name": fn, "tag_name": t["name"], "sha": t["commit"]["sha"]} for t in tags)
            resumos.append(resultado["resumo"])
            r = resultado["resumo"]
            print(
                f"[{i}/{len(repos)}] {fn} -> {r['releases_calculadas']} releases, {r['commits']} commits, "
                f"404: {r['releases_404']}",
                flush=True,
            )
    except KeyboardInterrupt:
        sys.exit("\nInterrompido. As respostas já feitas estão no cache: rode o mesmo comando para retomar.")

    salvar_csv(saida / "releases.csv", CAMPOS_RELEASES, todas_releases)
    salvar_csv(saida / "commits_releases.csv", CAMPOS_COMMITS, todos_commits)
    salvar_csv(saida / "tags.csv", CAMPOS_TAGS, todas_tags)
    salvar_csv(saida / "lead_time_repos.csv", CAMPOS_RESUMO, resumos)

    total_404 = sum(r["releases_404"] for r in resumos)
    print(
        f"\n{len(resumos)} repositórios processados. Releases puladas por 404: {total_404}.\n"
        f"Salvo em {saida}/ (releases.csv, commits_releases.csv, tags.csv, lead_time_repos.csv). "
        f"Chamadas à API: {client.chamadas} | respostas do cache: {client.cache_hits}"
    )


if __name__ == "__main__":
    main()
