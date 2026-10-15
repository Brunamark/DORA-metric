#!/usr/bin/env python3
"""
Lab03S02 - amostra-ouro: sorteio dos repositórios e releases e geração das planilhas.

A amostra-ouro é o conjunto rotulado por pessoas que serve de referência para medir o
quanto as heurísticas automáticas erram (RQ 03 b, tipo do projeto na RQ 06 e ameaças à
validade). Este script:

  1. Lê a amostra final (repos_selecionados.csv) e as releases coletadas pelo Card B
     (releases.csv).
  2. Considera release avaliável a que foi publicada na janela, tem release anterior (é
     a base do compare) e teve o compare resolvido (status ok ou sem_commits; tag_404 e
     erros de HTTP não têm lista de commits para o avaliador ler).
  3. Sorteia 60 repositórios, com semente fixa, entre os que têm pelo menos 5 releases
     avaliáveis. Para cada um, sorteia 5 releases avaliáveis, também com semente fixa.
  4. Grava validacao/amostra_ouro.csv, validacao/sorteio.json e uma planilha idêntica por
     integrante (validacao/rotulos_<integrante>.csv), com links diretos e as colunas a
     preencher. As planilhas NÃO trazem nada calculado pela heurística: o avaliador não
     pode ver a saída dela.

Reprodutibilidade: a semente é a constante SEED. O sorteio ordena repositórios e releases
antes de sortear, então a ordem das linhas dos CSVs de entrada não muda o resultado.
Rodar duas vezes gera exatamente as mesmas 60 x 5 releases.

O script recusa sobrescrever planilhas já existentes (podem ter rótulos preenchidos);
use --forcar só se for refazer o sorteio do zero.

Uso:
    python src/amostra_ouro.py --integrantes ana bruno carla
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

from validar_rotulos import (
    ARQUIVO_AMOSTRA,
    COLUNAS_AMOSTRA,
    COLUNAS_PLANILHA,
    DIMENSOES,
    PASTA_VALIDACAO,
    RAIZ,
    caminho_planilha,
    ler_csv,
)

SEED = 42  # semente do sorteio (documentada aqui, como pede o enunciado)
N_REPOS = 60
N_RELEASES = 5
# Status de releases.csv (Card B) cuja lista de commits o avaliador consegue abrir no GitHub
STATUS_AVALIAVEIS = frozenset({"ok", "sem_commits"})
CAMINHO_REPOS = RAIZ / "src" / "data" / "repos_selecionados.csv"
CAMINHO_RELEASES = RAIZ / "src" / "data" / "releases.csv"
ARQUIVO_SORTEIO = "sorteio.json"
# Caracteres que podem aparecer sem codificar numa tag dentro da URL (ex.: @scope/pacote@1.0.0)
_SEGUROS_URL = "/@:+"


def releases_avaliaveis(releases: pd.DataFrame) -> pd.DataFrame:
    """Releases do releases.csv que podem entrar no sorteio (ver o docstring do módulo)."""
    na_janela = releases["na_janela"].str.strip().str.lower() == "true"
    com_anterior = releases["tag_anterior"].str.strip() != ""
    compare_ok = releases["status"].str.strip().isin(STATUS_AVALIAVEIS)
    return releases[na_janela & com_anterior & compare_ok].copy()


def sortear_amostra_ouro(
    repos: pd.DataFrame,
    releases: pd.DataFrame,
    n_repos: int = N_REPOS,
    n_releases: int = N_RELEASES,
    seed: int = SEED,
) -> tuple[pd.DataFrame, dict]:
    """Sorteia n_repos repositórios e n_releases releases avaliáveis de cada um.

    Retorna (amostra, resumo). `amostra` tem as colunas repo, tag e tag_anterior, ordenada por
    repositório e data de publicação. Levanta ValueError se não houver repositórios suficientes."""
    avaliaveis = releases_avaliaveis(releases)
    avaliaveis = avaliaveis[avaliaveis["full_name"].isin(repos["full_name"])]
    por_repo = avaliaveis.groupby("full_name").size()
    elegiveis = por_repo[por_repo >= n_releases].index.sort_values()

    resumo = {
        "seed": seed,
        "n_repos": n_repos,
        "n_releases_por_repo": n_releases,
        "repos_na_amostra_final": int(repos["full_name"].nunique()),
        "repos_com_releases_avaliaveis": int(len(por_repo)),
        "repos_elegiveis": int(len(elegiveis)),
        "releases_avaliaveis_total": int(len(avaliaveis)),
    }
    if len(elegiveis) < n_repos:
        raise ValueError(
            f"só {len(elegiveis)} repositórios têm {n_releases} ou mais releases avaliáveis; "
            f"são necessários {n_repos}. Confira se releases.csv cobre a amostra final."
        )

    # df.sample(n=60, random_state=42): repositórios em ordem alfabética para o sorteio
    # não depender da ordem das linhas do CSV
    sorteados = pd.Series(elegiveis).sample(n=n_repos, random_state=seed).sort_values()

    rng = np.random.RandomState(seed)  # um gerador só, consumido na ordem dos repositórios
    partes = []
    for repo in sorteados:
        candidatas = avaliaveis[avaliaveis["full_name"] == repo].sort_values(["published_at", "tag_name"])
        partes.append(candidatas.sample(n=n_releases, random_state=rng).sort_values(["published_at", "tag_name"]))

    sorteio = pd.concat(partes)
    amostra = pd.DataFrame(
        {"repo": sorteio["full_name"], "tag": sorteio["tag_name"], "tag_anterior": sorteio["tag_anterior"]}
    ).reset_index(drop=True)
    return amostra, resumo


def links(repo: str, tag: str, tag_anterior: str) -> tuple[str, str, str]:
    """Links diretos para o repositório, a página da release e a lista de commits entre as releases."""
    base = f"https://github.com/{repo}"
    tag_url = quote(tag, safe=_SEGUROS_URL)
    anterior_url = quote(tag_anterior, safe=_SEGUROS_URL)
    return base, f"{base}/releases/tag/{tag_url}", f"{base}/compare/{anterior_url}...{tag_url}"


def montar_planilha(amostra: pd.DataFrame) -> pd.DataFrame:
    """Planilha a ser preenchida: identificação, links e as colunas vazias dos rótulos.
    Nenhuma coluna vem da heurística."""
    linhas = []
    for repo, tag, anterior in zip(amostra["repo"], amostra["tag"], amostra["tag_anterior"]):
        link_repo, link_release, link_commits = links(repo, tag, anterior)
        linhas.append({
            "repo": repo, "tag": tag, "tag_anterior": anterior,
            "link_repo": link_repo, "link_release": link_release, "link_commits": link_commits,
            **{dimensao: "" for dimensao in DIMENSOES},
        })
    return pd.DataFrame(linhas, columns=list(COLUNAS_PLANILHA))


def gravar(saida: Path, integrantes: list[str], amostra: pd.DataFrame, resumo: dict, forcar: bool) -> list[Path]:
    """Grava amostra_ouro.csv, sorteio.json e as planilhas. Recusa sobrescrever sem `forcar`."""
    saida = Path(saida)
    destinos = [saida / ARQUIVO_AMOSTRA, saida / ARQUIVO_SORTEIO] + [
        caminho_planilha(saida, nome) for nome in integrantes
    ]
    existentes = [d for d in destinos if d.exists()]
    if existentes and not forcar:
        nomes = ", ".join(d.name for d in existentes)
        raise FileExistsError(
            f"já existem em {saida}: {nomes}. Podem ter rótulos preenchidos; "
            "use --forcar só para refazer o sorteio do zero."
        )

    saida.mkdir(parents=True, exist_ok=True)
    amostra.loc[:, list(COLUNAS_AMOSTRA)].to_csv(saida / ARQUIVO_AMOSTRA, index=False, encoding="utf-8")
    (saida / ARQUIVO_SORTEIO).write_text(json.dumps(resumo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    planilha = montar_planilha(amostra)
    for nome in integrantes:  # utf-8-sig: o Excel reconhece os acentos
        planilha.to_csv(caminho_planilha(saida, nome), index=False, encoding="utf-8-sig")
    return destinos


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - sorteio da amostra-ouro e planilhas de rótulos")
    ap.add_argument("--integrantes", nargs="+", required=True, help="nomes dos avaliadores (um arquivo cada)")
    ap.add_argument("--repos", default=str(CAMINHO_REPOS), help="CSV da amostra final (coluna full_name)")
    ap.add_argument("--releases", default=str(CAMINHO_RELEASES), help="releases.csv gerado por coleta_releases.py")
    ap.add_argument("--saida", default=str(PASTA_VALIDACAO), help="pasta de saída")
    ap.add_argument("--forcar", action="store_true", help="sobrescreve arquivos existentes (apaga rótulos!)")
    args = ap.parse_args()

    invalidos = [n for n in args.integrantes if not re.fullmatch(r"[\w-]+", n)]
    if invalidos or len(set(args.integrantes)) != len(args.integrantes):
        sys.exit("--integrantes: use nomes únicos só com letras, números, _ e - (viram o nome do arquivo)")

    for caminho in (args.repos, args.releases):
        if not Path(caminho).exists():
            sys.exit(f"{caminho} não existe. Rode a coleta (selecao_repos.py e coleta_releases.py) antes.")
    repos = ler_csv(Path(args.repos))
    releases = ler_csv(Path(args.releases))

    try:
        amostra, resumo = sortear_amostra_ouro(repos, releases)
        gravar(Path(args.saida), args.integrantes, amostra, resumo, args.forcar)
    except (ValueError, FileExistsError) as exc:
        sys.exit(str(exc))

    print(
        f"Sorteados {amostra['repo'].nunique()} repositórios x {N_RELEASES} releases = {len(amostra)} linhas "
        f"(semente {SEED}; {resumo['repos_elegiveis']} repositórios elegíveis de "
        f"{resumo['repos_na_amostra_final']} na amostra final).\n"
        f"Planilhas em {args.saida}: " + ", ".join(f"rotulos_{n}.csv" for n in args.integrantes)
    )


if __name__ == "__main__":
    main()
