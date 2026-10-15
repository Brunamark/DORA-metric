#!/usr/bin/env python3
"""
Lab03S02 - validação das planilhas de rótulos da amostra-ouro.

Antes de calcular kappa ou consenso, cada planilha validacao/rotulos_<integrante>.csv
precisa estar completa e só usar os valores permitidos. Este módulo:

  - confere colunas, linhas (as mesmas 60 x 5 releases do sorteio, sem repetição) e
    células vazias;
  - confere os valores de cada dimensão:
        tipo_projeto    biblioteca/framework | aplicação/serviço | ferramenta CLI | outro
        releases_reais  sim | não | incerto
        corretiva       sim | não
    (maiúsculas, acentos e espaços nas pontas são tolerados: "Nao " vale "não");
  - confere que tipo_projeto e releases_reais, que são julgamentos do repositório, têm o
    mesmo valor nas 5 linhas de cada repositório;
  - devolve os rótulos normalizados, que alimentam concordancia.py e consenso.py.

Aceita CSV separado por vírgula ou ponto e vírgula (o Excel em português salva com ";").

Uso:
    python src/validar_rotulos.py --integrantes ana bruno carla
"""

import argparse
import io
import sys
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PASTA_VALIDACAO = RAIZ / "validacao"
ARQUIVO_AMOSTRA = "amostra_ouro.csv"

# Dimensões rotuladas. "repo": um julgamento por repositório (repetido nas linhas do
# repositório); "release": um julgamento por release sorteada.
DIMENSOES = ("tipo_projeto", "releases_reais", "corretiva")
NIVEL = {"tipo_projeto": "repo", "releases_reais": "repo", "corretiva": "release"}
VALORES_PERMITIDOS = {
    "tipo_projeto": ("biblioteca/framework", "aplicação/serviço", "ferramenta CLI", "outro"),
    "releases_reais": ("sim", "não", "incerto"),
    "corretiva": ("sim", "não"),
}

COLUNAS_CHAVE = ("repo", "tag")
COLUNAS_LINKS = ("link_repo", "link_release", "link_commits")
COLUNAS_PLANILHA = ("repo", "tag", "tag_anterior", *COLUNAS_LINKS, *DIMENSOES)
COLUNAS_AMOSTRA = ("repo", "tag", "tag_anterior")


class RotulosInvalidos(Exception):
    """Planilhas incompletas ou com valores fora do permitido. `erros` = {integrante: [msgs]}."""

    def __init__(self, erros: dict[str, list[str]]):
        self.erros = erros
        super().__init__(formatar_erros(erros))


def _chave(texto: str) -> str:
    """Forma comparável: sem acentos, minúscula, espaços internos reduzidos."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.casefold().split())


_CANONICO = {
    dimensao: {_chave(valor): valor for valor in valores}
    for dimensao, valores in VALORES_PERMITIDOS.items()
}


def normalizar_valor(dimensao: str, valor: str) -> str | None:
    """Valor permitido equivalente a `valor`, ou None se não existir (inclui vazio)."""
    return _CANONICO[dimensao].get(_chave(valor))


def ler_csv(caminho: Path) -> pd.DataFrame:
    """Lê um CSV como texto, sem converter nada. Detecta vírgula ou ponto e vírgula."""
    texto = Path(caminho).read_text(encoding="utf-8-sig")
    cabecalho = texto.splitlines()[0] if texto.strip() else ""
    separador = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    df = pd.read_csv(io.StringIO(texto), sep=separador, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def caminho_planilha(pasta: Path, integrante: str) -> Path:
    return Path(pasta) / f"rotulos_{integrante}.csv"


def ler_amostra(pasta: Path) -> pd.DataFrame:
    """validacao/amostra_ouro.csv: as releases sorteadas (referência das planilhas)."""
    caminho = Path(pasta) / ARQUIVO_AMOSTRA
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe: rode amostra_ouro.py antes")
    return ler_csv(caminho)


# --------------------------------------------------------------------------
# Validação
# --------------------------------------------------------------------------
def validar_planilha(df: pd.DataFrame, amostra: pd.DataFrame) -> list[str]:
    """Lista de problemas da planilha (vazia = válida). `amostra` define as linhas esperadas.
    Os números de linha são os da planilha (cabeçalho = linha 1)."""
    ausentes = [c for c in COLUNAS_PLANILHA if c not in df.columns]
    if ausentes:
        return [f"colunas ausentes: {', '.join(ausentes)}"]

    erros = []
    chaves = list(zip(df["repo"].str.strip(), df["tag"].str.strip()))
    esperadas = set(zip(amostra["repo"], amostra["tag"]))

    repetidas = sorted({k for k in chaves if chaves.count(k) > 1})
    for repo, tag in repetidas:
        erros.append(f"release repetida: {repo} @ {tag}")
    for repo, tag in sorted(esperadas - set(chaves)):
        erros.append(f"linha faltando: {repo} @ {tag}")
    for repo, tag in sorted(set(chaves) - esperadas):
        erros.append(f"linha que não está na amostra sorteada: {repo} @ {tag}")

    for posicao, (_, linha) in enumerate(df.iterrows()):
        numero = posicao + 2
        for dimensao in DIMENSOES:
            bruto = linha[dimensao].strip()
            if not bruto:
                erros.append(f"linha {numero}: coluna '{dimensao}' vazia")
            elif normalizar_valor(dimensao, bruto) is None:
                permitidos = ", ".join(VALORES_PERMITIDOS[dimensao])
                erros.append(
                    f"linha {numero}: valor '{bruto}' inválido em '{dimensao}' (permitidos: {permitidos})"
                )

    for dimensao in (d for d in DIMENSOES if NIVEL[d] == "repo"):
        normalizados = df[dimensao].map(lambda v: normalizar_valor(dimensao, v) or "")
        por_repo = normalizados[normalizados != ""].groupby(df["repo"].str.strip()).nunique()
        for repo in por_repo[por_repo > 1].index:
            erros.append(
                f"'{dimensao}' tem valores diferentes nas linhas de {repo} "
                "(é um julgamento do repositório: use o mesmo valor nas 5 linhas)"
            )
    return erros


def normalizar_planilha(df: pd.DataFrame) -> pd.DataFrame:
    """Cópia com chaves sem espaços nas pontas e rótulos nos valores canônicos.
    Só chamar depois de validar_planilha devolver lista vazia."""
    df = df.copy()
    for coluna in COLUNAS_CHAVE:
        df[coluna] = df[coluna].str.strip()
    for dimensao in DIMENSOES:
        df[dimensao] = df[dimensao].map(lambda v, d=dimensao: normalizar_valor(d, v))
    return df


def formatar_erros(erros: dict[str, list[str]], limite: int = 15) -> str:
    partes = []
    for integrante, lista in erros.items():
        partes.append(f"rotulos_{integrante}.csv: {len(lista)} problema(s)")
        partes.extend(f"  - {erro}" for erro in lista[:limite])
        if len(lista) > limite:
            partes.append(f"  ... e mais {len(lista) - limite}")
    return "\n".join(partes)


def validar_todas(pasta: Path, integrantes: list[str]) -> dict[str, list[str]]:
    """Problemas de cada planilha: {integrante: [mensagens]}. Só inclui quem tem problemas."""
    amostra = ler_amostra(pasta)
    erros = {}
    for integrante in integrantes:
        caminho = caminho_planilha(pasta, integrante)
        if not caminho.exists():
            erros[integrante] = [f"arquivo {caminho.name} não existe"]
            continue
        problemas = validar_planilha(ler_csv(caminho), amostra)
        if problemas:
            erros[integrante] = problemas
    return erros


def carregar_rotulos(pasta: Path, integrantes: list[str]) -> dict[str, pd.DataFrame]:
    """Planilhas validadas e normalizadas, {integrante: DataFrame}.
    Levanta RotulosInvalidos se alguma estiver incompleta ou com valor fora do permitido."""
    erros = validar_todas(pasta, integrantes)
    if erros:
        raise RotulosInvalidos(erros)
    return {
        integrante: normalizar_planilha(ler_csv(caminho_planilha(pasta, integrante)))
        for integrante in integrantes
    }


def tabela_itens(rotulos: dict[str, pd.DataFrame], dimensao: str) -> pd.DataFrame:
    """Itens avaliados em uma dimensão: uma linha por item (repositório ou release) e uma
    coluna por avaliador. Índice = (repo, tag); tag vazia nas dimensões do repositório."""
    colunas = {}
    for integrante, df in rotulos.items():
        if NIVEL[dimensao] == "repo":
            parte = df.drop_duplicates("repo").assign(tag="")
        else:
            parte = df
        colunas[integrante] = parte.set_index(list(COLUNAS_CHAVE))[dimensao]
    return pd.DataFrame(colunas).sort_index()


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - valida as planilhas de rótulos")
    ap.add_argument("--integrantes", nargs="+", required=True, help="nomes usados em rotulos_<nome>.csv")
    ap.add_argument("--pasta", default=str(PASTA_VALIDACAO), help="pasta com as planilhas")
    args = ap.parse_args()

    try:
        erros = validar_todas(Path(args.pasta), args.integrantes)
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    if erros:
        print(formatar_erros(erros), file=sys.stderr)
        sys.exit(1)
    print(f"OK: {len(args.integrantes)} planilhas completas e com valores permitidos.")


if __name__ == "__main__":
    main()
