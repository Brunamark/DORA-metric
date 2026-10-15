#!/usr/bin/env python3
"""
Lab03S02 - concordância entre os avaliadores da amostra-ouro (kappa de Fleiss).

Para cada uma das três dimensões rotuladas (tipo_projeto, releases_reais, corretiva),
calcula o kappa de Fleiss entre os avaliadores com aggregate_raters + fleiss_kappa do
statsmodels e interpreta o valor pela escala de Landis & Koch (1977).

Itens avaliados:
  tipo_projeto, releases_reais   um por repositório (60)
  corretiva                      um por release sorteada (300)

O kappa corrige a concordância que aconteceria por acaso. Se todos os avaliadores usarem
sempre a mesma categoria, o kappa é indefinido (a concordância esperada por acaso já é
100%): a tabela mostra "indefinido" e a % de itens unânimes.

Saídas em validacao/: kappa.csv e kappa.md (tabela para o artigo).

Uso:
    python src/concordancia.py --integrantes ana bruno carla
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa

from validar_rotulos import DIMENSOES, PASTA_VALIDACAO, RotulosInvalidos, carregar_rotulos, tabela_itens

NOMES_DIMENSOES = {
    "tipo_projeto": "Tipo do projeto",
    "releases_reais": "Releases são entregas reais",
    "corretiva": "Release corretiva",
}
CAMPOS_KAPPA = [
    "dimensao", "n_itens", "n_avaliadores", "n_categorias_usadas",
    "pct_itens_unanimes", "kappa", "interpretacao",
]

# Landis & Koch (1977): limite superior de cada faixa
FAIXAS_LANDIS_KOCH = [
    (0.20, "leve"),
    (0.40, "razoável"),
    (0.60, "moderada"),
    (0.80, "substancial"),
]


def interpretar_kappa(kappa: float) -> str:
    """Interpretação de Landis & Koch (1977): < 0 pobre; 0-0,20 leve; 0,21-0,40 razoável;
    0,41-0,60 moderada; 0,61-0,80 substancial; 0,81-1 quase perfeita."""
    if kappa is None or math.isnan(kappa):
        return "indefinida"
    if kappa < 0:
        return "pobre"
    for limite, nome in FAIXAS_LANDIS_KOCH:
        if kappa <= limite:
            return nome
    return "quase perfeita"


def kappa_fleiss(avaliacoes) -> float:
    """Kappa de Fleiss. `avaliacoes`: uma linha por item, uma coluna por avaliador, com o
    rótulo dado (qualquer valor comparável). NaN se todos usarem sempre a mesma categoria."""
    dados = np.asarray(avaliacoes)
    if dados.ndim != 2 or dados.shape[0] < 1 or dados.shape[1] < 2:
        raise ValueError("avaliacoes precisa ter ao menos 1 item (linha) e 2 avaliadores (colunas)")
    if len(np.unique(dados)) < 2:
        return float("nan")
    tabela, _ = aggregate_raters(dados)
    return float(fleiss_kappa(tabela, method="fleiss"))


def calcular_kappas(rotulos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Uma linha por dimensão, com as colunas de CAMPOS_KAPPA."""
    linhas = []
    for dimensao in DIMENSOES:
        itens = tabela_itens(rotulos, dimensao)
        matriz = itens.to_numpy()
        kappa = kappa_fleiss(matriz)
        unanimes = (itens.nunique(axis=1) == 1).mean()
        linhas.append({
            "dimensao": dimensao,
            "n_itens": len(itens),
            "n_avaliadores": itens.shape[1],
            "n_categorias_usadas": int(len(np.unique(matriz))),
            "pct_itens_unanimes": round(100 * float(unanimes), 1),
            "kappa": "" if math.isnan(kappa) else round(kappa, 4),
            "interpretacao": interpretar_kappa(kappa),
        })
    return pd.DataFrame(linhas, columns=CAMPOS_KAPPA)


def tabela_markdown(kappas: pd.DataFrame) -> str:
    """Tabela em Markdown para o artigo (decimais com vírgula, como no texto)."""
    linhas = [
        "| Dimensão | Itens | Avaliadores | Itens unânimes (%) | κ de Fleiss | Interpretação (Landis & Koch, 1977) |",
        "|---|---|---|---|---|---|",
    ]
    for _, k in kappas.iterrows():
        valor = "indefinido" if k["kappa"] == "" else f"{float(k['kappa']):.3f}".replace(".", ",")
        unanimes = f"{float(k['pct_itens_unanimes']):.1f}".replace(".", ",")
        linhas.append(
            f"| {NOMES_DIMENSOES[k['dimensao']]} | {k['n_itens']} | {k['n_avaliadores']} | "
            f"{unanimes} | {valor} | {k['interpretacao']} |"
        )
    return "\n".join(linhas) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - kappa de Fleiss das três dimensões")
    ap.add_argument("--integrantes", nargs="+", required=True, help="nomes usados em rotulos_<nome>.csv")
    ap.add_argument("--pasta", default=str(PASTA_VALIDACAO), help="pasta com as planilhas e as saídas")
    args = ap.parse_args()

    pasta = Path(args.pasta)
    try:
        rotulos = carregar_rotulos(pasta, args.integrantes)
    except (RotulosInvalidos, FileNotFoundError) as exc:
        sys.exit(f"Planilhas inválidas, kappa não calculado:\n{exc}")

    kappas = calcular_kappas(rotulos)
    kappas.to_csv(pasta / "kappa.csv", index=False, encoding="utf-8")
    markdown = tabela_markdown(kappas)
    (pasta / "kappa.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Salvo em {pasta}/ (kappa.csv, kappa.md)")


if __name__ == "__main__":
    main()
