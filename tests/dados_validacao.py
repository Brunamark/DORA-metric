"""Dados sintéticos para os testes da amostra-ouro, no formato dos CSVs do Card B e do Card A."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from amostra_ouro import gravar, sortear_amostra_ouro
from validar_rotulos import DIMENSOES, ler_csv

CAMPOS_RELEASES = [
    "full_name", "tag_name", "draft", "prerelease", "published_at",
    "na_janela", "tag_anterior", "status", "n_commits", "total_commits_api",
    "lead_time_release_dias",
]
INTEGRANTES = ["ana", "bruno", "carla"]
INICIO_JANELA = datetime(2025, 10, 1, tzinfo=timezone.utc)


def nome_repo(i: int) -> str:
    return f"org{i:03d}/proj{i:03d}"


def fazer_repos(n: int = 80) -> pd.DataFrame:
    """Amostra final fictícia (coluna full_name, como em repos_selecionados.csv)."""
    return pd.DataFrame({"full_name": [nome_repo(i) for i in range(n)], "stars": ["1000"] * n}, dtype=str)


def fazer_releases(repos: pd.DataFrame, por_repo: int = 8, **excecoes) -> pd.DataFrame:
    """releases.csv fictício: por repositório, `por_repo` releases na janela (a primeira é
    `primeira_release`, sem anterior) e uma release antiga fora da janela.
    `excecoes`: {indice_do_repo: n_avaliaveis} reduz as releases avaliáveis de repos específicos
    (as demais viram tag_404), ex.: fazer_releases(repos, r3=2) -> repo 3 fica com 2 avaliáveis."""
    reduzir = {int(k[1:]): v for k, v in excecoes.items()}
    linhas = []
    for i, repo in enumerate(repos["full_name"]):
        linhas.append(_linha(repo, "v0.9", INICIO_JANELA - timedelta(days=60), "", "fora_da_janela", False))
        for j in range(por_repo):
            tag = f"v1.{j}"
            anterior = "v0.9" if j == 0 else f"v1.{j - 1}"
            publicada = INICIO_JANELA + timedelta(days=10 * (j + 1))
            if j == 0:
                # primeira da janela: tem a v0.9 como anterior e é avaliável, como no Card B
                status = "ok"
            elif j % 4 == 3:
                status = "sem_commits"
            else:
                status = "ok"
            if i in reduzir and j >= reduzir[i]:
                status = "tag_404"
            linhas.append(_linha(repo, tag, publicada, anterior, status, True))
    return pd.DataFrame(linhas, columns=CAMPOS_RELEASES, dtype=str)


def _linha(repo, tag, publicada, anterior, status, na_janela) -> dict:
    return {
        "full_name": repo, "tag_name": tag, "draft": "False", "prerelease": "False",
        "published_at": publicada.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "na_janela": str(na_janela), "tag_anterior": anterior, "status": status,
        "n_commits": "3", "total_commits_api": "3", "lead_time_release_dias": "4.0",
    }


def sortear_e_gravar(pasta: Path, integrantes=None, n_repos: int = 8, n_releases: int = 5):
    """Sorteio pequeno e rápido já gravado em `pasta`. Retorna a amostra."""
    integrantes = integrantes or INTEGRANTES
    repos = fazer_repos(20)
    releases = fazer_releases(repos)
    amostra, resumo = sortear_amostra_ouro(repos, releases, n_repos=n_repos, n_releases=n_releases)
    gravar(pasta, integrantes, amostra, resumo, forcar=False)
    return amostra


def preencher(pasta: Path, integrante: str, rotulo) -> None:
    """Preenche a planilha do integrante. `rotulo(dimensao, repo, tag)` devolve o valor da célula."""
    caminho = Path(pasta) / f"rotulos_{integrante}.csv"
    df = ler_csv(caminho)
    for dimensao in DIMENSOES:
        df[dimensao] = [rotulo(dimensao, r, t) for r, t in zip(df["repo"], df["tag"])]
    df.to_csv(caminho, index=False, encoding="utf-8-sig")


def rotulo_padrao(dimensao: str, repo: str, tag: str) -> str:
    """Todos concordam: um valor fixo por dimensão, variando com o repositório."""
    n = int(repo[3:6])
    if dimensao == "tipo_projeto":
        return ["biblioteca/framework", "aplicação/serviço", "ferramenta CLI", "outro"][n % 4]
    if dimensao == "releases_reais":
        return ["sim", "não", "incerto"][n % 3]
    return "sim" if tag.endswith(("1", "3")) else "não"
