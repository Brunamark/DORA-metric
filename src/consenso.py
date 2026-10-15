#!/usr/bin/env python3
"""
Lab03S02 - consenso dos rótulos da amostra-ouro.

Regra automática: maioria simples dos rótulos dos avaliadores.
Quando não há maioria (caso 1-1-1), o item vai para reunião e a decisão final vem de
validacao/decisoes_reuniao.csv.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from validar_rotulos import DIMENSOES, PASTA_VALIDACAO, RotulosInvalidos, carregar_rotulos, ler_csv, normalizar_valor, tabela_itens

ARQUIVO_CONSENSO = "consenso.csv"
ARQUIVO_DECISOES = "decisoes_reuniao.csv"

CAMPOS_CONSENSO = ["dimensao", "repo", "tag", "votos", "rotulo_consenso", "decidido_em"]
CAMPOS_DECISOES = ["dimensao", "repo", "tag", "votos", "rotulo_reuniao", "observacao"]


def maioria_simples(votos: list[str]) -> str | None:
    contagem = Counter(votos)
    rotulo, n = contagem.most_common(1)[0]
    return rotulo if n > len(votos) / 2 else None


def formatar_votos(votos: dict[str, str]) -> str:
    return " | ".join(f"{nome}={votos[nome]}" for nome in sorted(votos))


def ler_decisoes(caminho: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    caminho = Path(caminho)
    if not caminho.exists():
        return {}

    df = ler_csv(caminho)
    faltantes = [c for c in CAMPOS_DECISOES if c not in df.columns]
    if faltantes:
        raise ValueError(f"colunas ausentes em {caminho.name}: {', '.join(faltantes)}")

    decisoes = {}
    for posicao, (_, linha) in enumerate(df.iterrows()):
        numero = posicao + 2
        dimensao = str(linha["dimensao"]).strip()
        repo = str(linha["repo"]).strip()
        tag = str(linha["tag"]).strip()
        rotulo_reuniao = str(linha["rotulo_reuniao"]).strip()
        observacao = str(linha["observacao"]).strip()

        if not rotulo_reuniao:
            continue

        if dimensao not in DIMENSOES:
            raise ValueError(f"linha {numero}: rótulo '{rotulo_reuniao}' inválido para '{dimensao}'")

        rotulo = normalizar_valor(dimensao, rotulo_reuniao)
        if rotulo is None:
            raise ValueError(f"linha {numero}: rótulo '{rotulo_reuniao}' inválido para '{dimensao}'")

        decisoes[(dimensao, repo, tag)] = {"rotulo": rotulo, "observacao": observacao}
    return decisoes


def construir_consenso(
    rotulos: dict[str, pd.DataFrame],
    decisoes_reuniao: dict[tuple[str, str, str], dict[str, str]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    decisoes_reuniao = decisoes_reuniao or {}
    linhas_consenso = []
    linhas_reuniao = []

    for dimensao in DIMENSOES:
        itens = tabela_itens(rotulos, dimensao)
        for (repo, tag), votos_serie in itens.iterrows():
            votos = votos_serie.to_dict()
            votos_lista = list(votos.values())
            votos_formatados = formatar_votos(votos)
            por_maioria = maioria_simples(votos_lista)

            if por_maioria is not None:
                linhas_consenso.append({
                    "dimensao": dimensao,
                    "repo": repo,
                    "tag": tag,
                    "votos": votos_formatados,
                    "rotulo_consenso": por_maioria,
                    "decidido_em": "maioria",
                })
                continue

            chave = (dimensao, repo, tag)
            decisao = decisoes_reuniao.get(chave, {})
            rotulo_reuniao = decisao.get("rotulo", "")
            observacao = decisao.get("observacao", "")

            linhas_consenso.append({
                "dimensao": dimensao,
                "repo": repo,
                "tag": tag,
                "votos": votos_formatados,
                "rotulo_consenso": rotulo_reuniao,
                "decidido_em": "reuniao",
            })
            linhas_reuniao.append({
                "dimensao": dimensao,
                "repo": repo,
                "tag": tag,
                "votos": votos_formatados,
                "rotulo_reuniao": rotulo_reuniao,
                "observacao": observacao,
            })

    consenso = pd.DataFrame(linhas_consenso, columns=CAMPOS_CONSENSO)
    reuniao = pd.DataFrame(linhas_reuniao, columns=CAMPOS_DECISOES)
    return consenso, reuniao


def pendentes(consenso: pd.DataFrame) -> pd.DataFrame:
    return consenso[(consenso["decidido_em"] == "reuniao") & (consenso["rotulo_consenso"] == "")]


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - consenso dos rótulos da amostra-ouro")
    ap.add_argument("--integrantes", nargs="+", required=True, help="nomes usados em rotulos_<nome>.csv")
    ap.add_argument("--pasta", default=str(PASTA_VALIDACAO), help="pasta com as planilhas e as saídas")
    args = ap.parse_args()

    pasta = Path(args.pasta)
    try:
        rotulos = carregar_rotulos(pasta, args.integrantes)
        decisoes = ler_decisoes(pasta / ARQUIVO_DECISOES)
    except (RotulosInvalidos, FileNotFoundError, ValueError) as exc:
        sys.exit(f"Consenso não calculado:\n{exc}")

    consenso, reuniao = construir_consenso(rotulos, decisoes)
    consenso.to_csv(pasta / ARQUIVO_CONSENSO, index=False, encoding="utf-8")
    reuniao.to_csv(pasta / ARQUIVO_DECISOES, index=False, encoding="utf-8")

    n_pendentes = len(pendentes(consenso))
    if n_pendentes:
        unidade = "caso" if n_pendentes == 1 else "casos"
        sys.exit(f"{n_pendentes} {unidade} ainda aguardam decisão da reunião")

    print("Consenso completo.")
    print(f"Salvo em {pasta}/ ({ARQUIVO_CONSENSO}, {ARQUIVO_DECISOES})")


if __name__ == "__main__":
    main()
