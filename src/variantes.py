#!/usr/bin/env python3
"""
Lab03S02 - variantes de unidade de deploy da RQ 07 (issue #8).

Datas das tags (unidade "tag", combinação C3):
  A data de uma tag é a data do commit para o qual ela aponta (enunciado, seção 4). A
  listagem REST de /tags, feita pela etapa releases, já traz o sha desse commit (inclusive
  nas tags anotadas). Esta etapa lê o tags.csv, consulta via GraphQL a data de commit
  (committedDate) de 100 shas por chamada e regrava o tags.csv com a coluna commit_date.
  Várias tags no mesmo commit geram uma consulta só.

Não altera as saídas das outras etapas além da coluna commit_date do tags.csv; por isso
precisa rodar depois da etapa releases (o pipeline garante a ordem).

Saídas em --saida:
  tags.csv              tags de cada repositório, agora com commit_date
  variantes_repos.csv   resumo por repositório

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

from selecao_repos import (
    CACHE_PADRAO,
    DADOS_PADRAO,
    ErroDeToken,
    GitHubClient,
    ler_repos,
    ler_token,
    parse_janela,
    salvar_csv,
)

TAMANHO_LOTE = 100   # shas por consulta GraphQL
RE_SHA = re.compile(r"^[0-9a-f]{40}$")

CAMPOS_TAGS = ["full_name", "tag_name", "sha", "commit_date"]
CAMPOS_RESUMO = ["full_name", "status_tags_datas", "tags", "tags_sem_data"]


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
    """Linhas do tags.csv do repositório com commit_date e o resumo da etapa."""
    status, datas = datas_dos_commits(client, fn, (t["sha"] for t in tags))
    linhas = [
        {"full_name": fn, "tag_name": t["tag_name"], "sha": t["sha"], "commit_date": datas.get(t["sha"], "")}
        for t in tags
    ]
    resumo = {
        "full_name": fn,
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
    """Data as tags de todos os repositórios e grava os CSVs. Retorna os resumos."""
    tags_por_repo = ler_tags(saida / "tags.csv")
    todas_tags, resumos = [], []
    for i, repo in enumerate(repos, 1):
        fn = repo["full_name"]
        linhas, resumo = datar_tags(client, fn, tags_por_repo.get(fn, []))
        todas_tags.extend(linhas)
        resumos.append(resumo)
        problemas = [f"status_tags_datas={resumo['status_tags_datas']}"] if resumo["status_tags_datas"] != "ok" else []
        if resumo["tags_sem_data"]:
            problemas.append(f"tags_sem_data={resumo['tags_sem_data']}")
        print(
            f"[{i}/{len(repos)}] {fn} -> {resumo['tags']} tags"
            + (f" | {', '.join(problemas)}" if problemas else ""),
            flush=True,
        )

    # Tags de repositórios fora da lista (ex.: --repos com um subconjunto) não se perdem
    processados = {r["full_name"] for r in repos}
    for fn, tags in tags_por_repo.items():
        if fn not in processados:
            todas_tags.extend({campo: t.get(campo, "") for campo in CAMPOS_TAGS} for t in tags)

    salvar_csv(saida / "tags.csv", CAMPOS_TAGS, todas_tags)
    salvar_csv(saida / "variantes_repos.csv", CAMPOS_RESUMO, resumos)
    print(
        f"\n{len(resumos)} repositórios processados "
        f"({sum(r['status_tags_datas'] != 'ok' for r in resumos)} com erro ao datar tags). "
        f"Tags sem data: {sum(r['tags_sem_data'] for r in resumos)} de {sum(r['tags'] for r in resumos)}.\n"
        f"Salvo em {saida}/ (tags.csv, variantes_repos.csv). "
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
