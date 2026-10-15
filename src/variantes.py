#!/usr/bin/env python3
"""
Lab03S02 - variantes de unidade de deploy da RQ 07 (issue #8).

Release + pré-release (combinação C2):
  Mesma regra do lead time da definição principal (coleta_releases.py), mas a unidade de
  deploy passa a incluir as pré-releases: entre todas as releases não draft, ordenadas por
  published_at, cada uma tem como anterior a imediatamente anterior. A primeira da história
  é ignorada. Para cada release não draft da janela, os commits vêm de
  compare/{anterior}...{release}. Reaproveita listar_releases() e commits_entre() da etapa
  releases: a listagem e os pares iguais aos da definição principal saem do cache, e só os
  pares que envolvem pré-releases geram chamadas novas.

Datas das tags (unidade "tag", combinação C3):
  A data de uma tag é a data do commit para o qual ela aponta (enunciado, seção 4). A
  listagem REST de /tags, feita pela etapa releases, já traz o sha desse commit (inclusive
  nas tags anotadas). Esta etapa lê o tags.csv, consulta via GraphQL a data de commit
  (committedDate) de 100 shas por chamada e regrava o tags.csv com a coluna commit_date.
  Várias tags no mesmo commit geram uma consulta só.

Não altera as saídas das outras etapas além da coluna commit_date do tags.csv; por isso
precisa rodar depois da etapa releases (o pipeline garante a ordem).

Saídas em --saida:
  releases_c2.csv       releases não draft da janela, com o par e o lead time da C2
  tags.csv              tags de cada repositório, agora com commit_date
  variantes_repos.csv   resumo por repositório (C2 e datas das tags)

Uso (normalmente pelo pipeline: python src/pipeline.py, ver README):
    export GITHUB_TOKEN=ghp_xxx
    python src/variantes.py --inicio 2025-10-01 --fim 2026-10-01
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

from coleta_releases import commits_entre, listar_releases
from metricas import (
    lead_time_commit,
    lead_time_release,
    mediana_lead_time_commit,
    mediana_lead_time_release,
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

TAMANHO_LOTE = 100   # shas por consulta GraphQL
RE_SHA = re.compile(r"^[0-9a-f]{40}$")

CAMPOS_RELEASES_C2 = [
    "full_name", "tag_name", "prerelease", "published_at", "tag_anterior",
    "status", "n_commits", "total_commits_api", "lead_time_release_dias",
]
CAMPOS_TAGS = ["full_name", "tag_name", "sha", "commit_date"]
CAMPOS_RESUMO_C2 = [
    "status_releases_c2", "releases_na_janela_c2", "releases_calculadas_c2",
    "releases_sem_commits_c2", "releases_404_c2", "releases_erro_c2",
    "releases_commits_incompletos_c2", "commits_c2", "commits_lead_time_negativo_c2",
    "lead_time_release_mediana_dias_c2", "lead_time_commit_mediana_dias_c2",
]
CAMPOS_RESUMO_TAGS = ["status_tags_datas", "tags", "tags_sem_data"]
CAMPOS_RESUMO = ["full_name", *CAMPOS_RESUMO_C2, *CAMPOS_RESUMO_TAGS]


# --------------------------------------------------------------------------
# Release + pré-release (C2)
# --------------------------------------------------------------------------
def nao_draft(release: dict) -> bool:
    """Release publicada ou pré-release: a unidade de deploy da C2."""
    return not release.get("draft") and bool(release.get("published_at"))


def _resumo_c2_vazio() -> dict:
    resumo = {campo: 0 for campo in CAMPOS_RESUMO_C2}
    resumo.update({
        "status_releases_c2": "ok",
        "lead_time_release_mediana_dias_c2": "",
        "lead_time_commit_mediana_dias_c2": "",
    })
    return resumo


def lead_time_c2(client, fn: str, ini: datetime, fim: datetime) -> tuple[list[dict], dict]:
    """Linhas de releases_c2.csv (releases não draft da janela) e as colunas _c2 do resumo."""
    resumo = _resumo_c2_vazio()
    st, releases = listar_releases(client, fn, ini)
    if st != 200:
        resumo["status_releases_c2"] = f"erro_http_{st}"
        return [], resumo

    ordenadas = sorted((r for r in releases if nao_draft(r)), key=lambda r: parse_iso(r["published_at"]))
    linhas, para_medianas = [], []
    for i, r in enumerate(ordenadas):
        pub = parse_iso(r["published_at"])
        if not ini <= pub <= fim:
            continue
        resumo["releases_na_janela_c2"] += 1
        linha = {
            "full_name": fn,
            "tag_name": r["tag_name"],
            "prerelease": bool(r.get("prerelease")),
            "published_at": r["published_at"],
            "tag_anterior": "",
            "status": "",
            "n_commits": "",
            "total_commits_api": "",
            "lead_time_release_dias": "",
        }
        linhas.append(linha)
        if i == 0:
            linha["status"] = "primeira_release"
            continue
        anterior = ordenadas[i - 1]["tag_name"]
        linha["tag_anterior"] = anterior

        st, commits, total_api = commits_entre(client, fn, anterior, r["tag_name"])
        if st == 404:
            linha["status"] = "tag_404"
            resumo["releases_404_c2"] += 1
            continue
        if st != 200:
            linha["status"] = f"erro_http_{st}"
            resumo["releases_erro_c2"] += 1
            continue

        datas = [parse_iso(c["commit"]["author"]["date"]) for c in commits]
        linha["n_commits"] = len(datas)
        linha["total_commits_api"] = "" if total_api is None else total_api
        if total_api is not None and total_api != len(datas):
            resumo["releases_commits_incompletos_c2"] += 1
        if not datas:
            linha["status"] = "sem_commits"
            resumo["releases_sem_commits_c2"] += 1
            continue

        linha["status"] = "ok"
        linha["lead_time_release_dias"] = round(lead_time_release(pub, datas), 4)
        resumo["releases_calculadas_c2"] += 1
        resumo["commits_c2"] += len(datas)
        resumo["commits_lead_time_negativo_c2"] += sum(lt < 0 for lt in lead_time_commit(pub, datas))
        para_medianas.append((pub, datas))

    med_rel = mediana_lead_time_release(para_medianas)
    med_commit = mediana_lead_time_commit(para_medianas)
    resumo["lead_time_release_mediana_dias_c2"] = "" if med_rel is None else round(med_rel, 4)
    resumo["lead_time_commit_mediana_dias_c2"] = "" if med_commit is None else round(med_commit, 4)
    return linhas, resumo


# --------------------------------------------------------------------------
# Datas das tags (C3)
# --------------------------------------------------------------------------
def consulta_datas(shas: list[str]) -> str:
    """Consulta GraphQL com um alias por sha (c0, c1, ...). Os shas entram no texto da
    consulta, então só shas validados (40 caracteres hexadecimais) podem ser passados."""
    objetos = "\n".join(
        f'    c{i}: object(oid: "{sha}") {{ ... on Commit {{ committedDate }} }}'
        for i, sha in enumerate(shas)
    )
    return (
        "query($owner: String!, $name: String!) {\n"
        "  repository(owner: $owner, name: $name) {\n"
        f"{objetos}\n"
        "  }\n"
        "}"
    )


def datas_dos_commits(client, fn: str, shas) -> tuple[str, dict[str, str]]:
    """Data de commit de cada sha, em lotes de TAMANHO_LOTE. Retorna (status, {sha: data}).
    Sha inválido, inexistente ou que não é commit fica fora do dicionário."""
    owner, name = fn.split("/", 1)
    validos = sorted({s for s in shas if RE_SHA.match(s or "")})  # ordem fixa: chave de cache estável
    datas = {}
    for inicio in range(0, len(validos), TAMANHO_LOTE):
        lote = validos[inicio:inicio + TAMANHO_LOTE]
        st, corpo = client.graphql(consulta_datas(lote), {"owner": owner, "name": name})
        if st != 200:
            return f"erro_http_{st}", datas
        repositorio = ((corpo or {}).get("data") or {}).get("repository")
        if repositorio is None:
            tipos = sorted({e.get("type") or "SEM_TIPO" for e in (corpo or {}).get("errors") or []})
            return f"erro_graphql_{tipos[0] if tipos else 'SEM_DADOS'}", datas
        for i, sha in enumerate(lote):
            objeto = repositorio.get(f"c{i}") or {}
            if objeto.get("committedDate"):
                datas[sha] = objeto["committedDate"]
    return "ok", datas


def datar_tags(client, fn: str, tags: list[dict]) -> tuple[list[dict], dict]:
    """Linhas do tags.csv do repositório com commit_date e as colunas de tags do resumo."""
    status, datas = datas_dos_commits(client, fn, (t["sha"] for t in tags))
    linhas = [
        {"full_name": fn, "tag_name": t["tag_name"], "sha": t["sha"], "commit_date": datas.get(t["sha"], "")}
        for t in tags
    ]
    resumo = {
        "status_tags_datas": status,
        "tags": len(linhas),
        "tags_sem_data": sum(not linha["commit_date"] for linha in linhas),
    }
    return linhas, resumo


def ler_tags(caminho: Path) -> dict[str, list[dict]]:
    """tags.csv agrupado por repositório, na ordem do arquivo (ignora uma coluna
    commit_date de uma execução anterior: as datas são recalculadas, do cache)."""
    if not caminho.exists():
        sys.exit(f"{caminho} não existe: rode antes a etapa releases.")
    por_repo: dict[str, list[dict]] = {}
    with caminho.open(newline="", encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f):
            por_repo.setdefault(linha["full_name"], []).append(linha)
    return por_repo


# --------------------------------------------------------------------------
# Etapa do pipeline
# --------------------------------------------------------------------------
def executar(client, ini: datetime, fim: datetime, repos: list[dict], saida: Path) -> list[dict]:
    """Calcula a C2 e data as tags de todos os repositórios e grava os CSVs.
    Retorna os resumos (uma linha por repositório, mesmo quando a API falha)."""
    tags_por_repo = ler_tags(saida / "tags.csv")
    todas_releases_c2, todas_tags, resumos = [], [], []
    for i, repo in enumerate(repos, 1):
        fn = repo["full_name"]
        linhas_c2, resumo_c2 = lead_time_c2(client, fn, ini, fim)
        linhas_tags, resumo_tags = datar_tags(client, fn, tags_por_repo.get(fn, []))
        todas_releases_c2.extend(linhas_c2)
        todas_tags.extend(linhas_tags)
        r = {"full_name": fn, **resumo_c2, **resumo_tags}
        resumos.append(r)
        problemas = [
            f"{campo}={r[campo]}" for campo in ("status_releases_c2", "status_tags_datas") if r[campo] != "ok"
        ] + [
            f"{campo}={r[campo]}"
            for campo in ("releases_404_c2", "releases_erro_c2", "releases_commits_incompletos_c2", "tags_sem_data")
            if r[campo]
        ]
        print(
            f"[{i}/{len(repos)}] {fn} -> C2: {r['releases_calculadas_c2']} releases, {r['commits_c2']} commits"
            f" | {r['tags']} tags" + (f" | {', '.join(problemas)}" if problemas else ""),
            flush=True,
        )

    # Tags de repositórios fora da lista (ex.: --repos com um subconjunto) não se perdem
    processados = {r["full_name"] for r in repos}
    for fn, tags in tags_por_repo.items():
        if fn not in processados:
            todas_tags.extend({campo: t.get(campo, "") for campo in CAMPOS_TAGS} for t in tags)

    salvar_csv(saida / "releases_c2.csv", CAMPOS_RELEASES_C2, todas_releases_c2)
    salvar_csv(saida / "tags.csv", CAMPOS_TAGS, todas_tags)
    salvar_csv(saida / "variantes_repos.csv", CAMPOS_RESUMO, resumos)

    def total(campo):
        return sum(r[campo] for r in resumos)

    print(
        f"\n{len(resumos)} repositórios processados "
        f"({sum(r['status_releases_c2'] != 'ok' for r in resumos)} com erro ao listar releases, "
        f"{sum(r['status_tags_datas'] != 'ok' for r in resumos)} com erro ao datar tags). "
        f"C2: releases puladas por 404: {total('releases_404_c2')} | outros erros: {total('releases_erro_c2')} | "
        f"comparações incompletas: {total('releases_commits_incompletos_c2')}. "
        f"Tags sem data: {total('tags_sem_data')} de {total('tags')}.\n"
        f"Salvo em {saida}/ (releases_c2.csv, tags.csv, variantes_repos.csv). "
        f"Chamadas à API: {client.chamadas} | respostas do cache: {client.cache_hits}"
    )
    return resumos


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - variantes de unidade de deploy da RQ 07")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--repos", default=str(DADOS_PADRAO / "repos_selecionados.csv"),
                    help="CSV com a coluna full_name")
    ap.add_argument("--saida", default=str(DADOS_PADRAO), help="pasta dos CSVs (lê o tags.csv da etapa releases)")
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
