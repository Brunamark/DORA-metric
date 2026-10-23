#!/usr/bin/env python3
"""
Lab03S02 - dataset consolidado (issue #8).

Junta os resumos por repositório de todas as etapas num único CSV, com uma linha por
repositório da amostra final e todas as variantes das métricas:

  repos_selecionados.csv   metadados (seleção)                     -> base da junção
  lead_time_repos.csv      lead time (a) e (b) da C1 (releases)
  variantes_repos.csv      lead time (a) e (b) da C2 e datas das tags (variantes)
  tags.csv                 tags com commit_date: frequência na unidade tag (variantes)
  workflow_runs_repos.csv  CFR (a) e tempo de recuperação (runs)
  cfr_entrega_repos.csv    CFR (b) (corretivas) -> só com --incluir-cfr-b

A junção é pela esquerda: um repositório que falta numa fonte continua no dataset, com
as métricas vazias, e gera um aviso. A frequência de deploy (RQ 01) é calculada nas três
unidades de deploy da RQ 07 com metricas.frequencia_deploy (releases por semana).

O CFR (b) fica fora por padrão: ele depende da versão final da heurística corretiva
(issue #10), escolhida só depois das três rotulagens da amostra-ouro (rotulagem cega).
Quando entra, usa o pareamento e o critério padrão de metricas.

Não faz nenhuma chamada à API: roda sem token, a partir dos CSVs das outras etapas.

Uso (normalmente pelo pipeline: python src/pipeline.py, ver README):
    python src/consolidar.py --inicio 2025-10-01 --fim 2026-10-01 [--incluir-cfr-b]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from metricas import CRITERIO_PADRAO, PAREAMENTO_PADRAO, frequencia_deploy
from selecao_repos import DADOS_PADRAO, parse_iso, parse_janela

ARQUIVO_DATASET = "dataset.csv"
ARQUIVO_CFR_B = "cfr_entrega_repos.csv"

# Colunas de cada fonte que vão para o dataset: {coluna na fonte: coluna no dataset}
COLUNAS_REPOS = {
    "full_name": "full_name", "url": "url", "stars": "stars", "language": "language",
    "contributors": "contributors", "created_at": "created_at", "age_days": "age_days",
    "default_branch": "default_branch",
}
COLUNAS_LEAD_TIME = {
    "status_releases": "status_releases",
    "status_tags": "status_tags",
    "releases_na_janela": "releases_na_janela",
    "releases_404": "releases_404",
    "lead_time_release_mediana_dias": "lead_time_a_dias",
    "lead_time_commit_mediana_dias": "lead_time_b_dias",
}
COLUNAS_VARIANTES = {
    "status_releases_c2": "status_releases_c2",
    "status_tags_datas": "status_tags_datas",
    "releases_na_janela_c2": "releases_na_janela_c2",
    "releases_404_c2": "releases_404_c2",
    "lead_time_release_mediana_dias_c2": "lead_time_a_dias_c2",
    "lead_time_commit_mediana_dias_c2": "lead_time_b_dias_c2",
    "tags": "tags",
    "tags_sem_data": "tags_sem_data",
}
COLUNAS_RUNS = {
    "status_runs": "status_runs",
    "fatias_no_teto": "fatias_no_teto",
    "cfr_a": "cfr_a",
    "tempo_recuperacao_mediana_horas": "tempo_recuperacao_horas",
    "episodios": "episodios",
    "episodios_censurados": "episodios_censurados",
    "proporcao_censurados": "proporcao_censurados",
}
COLUNAS_CFR_B = {
    "status": "status_cfr_b",
    "cfr_b": "cfr_b",
    "releases_avaliadas": "releases_avaliadas_cfr_b",
    "releases_censuradas": "releases_censuradas_cfr_b",
}

# Fontes obrigatórias, na ordem da junção: (arquivo, colunas, etapa que gera o arquivo)
FONTES = [
    ("lead_time_repos.csv", COLUNAS_LEAD_TIME, "releases"),
    ("variantes_repos.csv", COLUNAS_VARIANTES, "variantes"),
    ("workflow_runs_repos.csv", COLUNAS_RUNS, "runs"),
]

COLUNAS_DATASET = [
    # metadados
    "full_name", "url", "stars", "language", "contributors", "created_at", "age_days", "default_branch",
    # RQ 01: frequência de deploy nas três unidades (releases por semana)
    "releases_na_janela", "releases_na_janela_c2", "tags_na_janela",
    "freq_deploy_release", "freq_deploy_release_pre", "freq_deploy_tag",
    # RQ 02: lead time em dias, C1 e C2
    "lead_time_a_dias", "lead_time_b_dias", "lead_time_a_dias_c2", "lead_time_b_dias_c2",
    # RQ 03 (a) e RQ 04
    "cfr_a", "tempo_recuperacao_horas", "episodios", "episodios_censurados", "proporcao_censurados",
    # qualidade dos dados
    "status_releases", "status_tags", "status_releases_c2", "status_tags_datas", "status_runs",
    "releases_404", "releases_404_c2", "tags", "tags_sem_data", "fatias_no_teto",
]
COLUNAS_DATASET_CFR_B = ["cfr_b", "releases_avaliadas_cfr_b", "releases_censuradas_cfr_b", "status_cfr_b"]

# Contagens: inteiros, mas vazias quando o repositório falta na fonte
COLUNAS_INTEIRAS = [
    "stars", "contributors", "age_days", "releases_na_janela", "releases_na_janela_c2", "tags_na_janela",
    "episodios", "episodios_censurados", "releases_404", "releases_404_c2", "tags", "tags_sem_data",
    "fatias_no_teto", "releases_avaliadas_cfr_b", "releases_censuradas_cfr_b",
]
CASAS_FREQUENCIA = 4


def ler_fonte(caminho: Path, etapa: str) -> pd.DataFrame:
    if not caminho.exists():
        sys.exit(f"{caminho} não existe: rode antes a etapa {etapa}.")
    return pd.read_csv(caminho, dtype={"full_name": str}, keep_default_na=False, na_values=[""])


def tags_na_janela(tags: pd.DataFrame, ini: datetime, fim: datetime) -> pd.Series:
    """Nº de tags por repositório com commit_date dentro da janela (tag sem data não conta)."""
    if "commit_date" not in tags.columns:
        sys.exit("tags.csv não tem a coluna commit_date: rode a etapa variantes depois de releases.")
    datas = tags["commit_date"].map(lambda t: parse_iso(t) if isinstance(t, str) else None)
    na_janela = datas.map(lambda d: d is not None and ini <= d <= fim)
    return na_janela.groupby(tags["full_name"]).sum().astype(int)


def _frequencia(n, status_ok: bool, ini: datetime, fim: datetime):
    """Releases por semana; vazio se a contagem não existe ou a coleta deu erro."""
    if not status_ok or pd.isna(n):
        return None
    return round(frequencia_deploy(int(n), ini, fim), CASAS_FREQUENCIA)


def _juntar(base: pd.DataFrame, fonte: pd.DataFrame, colunas: dict, nome: str) -> pd.DataFrame:
    parte = fonte.loc[:, ["full_name", *colunas]].rename(columns=colunas).drop_duplicates("full_name")
    faltando = sorted(set(base["full_name"]) - set(parte["full_name"]))
    if faltando:
        print(f"  aviso: {len(faltando)} repositório(s) sem linha em {nome} (métricas vazias): "
              + ", ".join(faltando[:5]) + (" ..." if len(faltando) > 5 else ""))
    return base.merge(parte, on="full_name", how="left")


def consolidar(saida: Path, ini: datetime, fim: datetime, incluir_cfr_b: bool = False) -> pd.DataFrame:
    """Monta o dataset (uma linha por repositório de repos_selecionados.csv)."""
    repos = ler_fonte(saida / "repos_selecionados.csv", "selecao")
    dataset = repos.loc[:, list(COLUNAS_REPOS)].rename(columns=COLUNAS_REPOS)

    for arquivo, colunas, etapa in FONTES:
        dataset = _juntar(dataset, ler_fonte(saida / arquivo, etapa), colunas, arquivo)

    contagem_tags = tags_na_janela(ler_fonte(saida / "tags.csv", "releases"), ini, fim)
    tags_ok = (dataset["status_tags"] == "ok") & (dataset["status_tags_datas"] == "ok")
    dataset["tags_na_janela"] = dataset["full_name"].map(contagem_tags).fillna(0).where(tags_ok)

    def frequencia(coluna, *status):
        return [
            _frequencia(n, all(s == "ok" for s in valores), ini, fim)
            for n, *valores in zip(dataset[coluna], *(dataset[s] for s in status))
        ]

    dataset["freq_deploy_release"] = frequencia("releases_na_janela", "status_releases")
    dataset["freq_deploy_release_pre"] = frequencia("releases_na_janela_c2", "status_releases_c2")
    dataset["freq_deploy_tag"] = frequencia("tags_na_janela", "status_tags", "status_tags_datas")

    colunas = list(COLUNAS_DATASET)
    if incluir_cfr_b:
        cfr_b = ler_fonte(saida / ARQUIVO_CFR_B, "corretivas")
        padrao = cfr_b[(cfr_b["pareamento"] == PAREAMENTO_PADRAO) & (cfr_b["criterio"] == CRITERIO_PADRAO)]
        dataset = _juntar(dataset, padrao, COLUNAS_CFR_B, f"{ARQUIVO_CFR_B} ({PAREAMENTO_PADRAO}/{CRITERIO_PADRAO})")
        colunas += COLUNAS_DATASET_CFR_B

    dataset = dataset.loc[:, colunas]
    for coluna in COLUNAS_INTEIRAS:
        if coluna in dataset.columns:
            dataset[coluna] = dataset[coluna].astype("Int64")
    return dataset


def executar(ini: datetime, fim: datetime, saida: Path, incluir_cfr_b: bool = False) -> pd.DataFrame:
    """Gera saida/dataset.csv. Retorna o dataset."""
    dataset = consolidar(saida, ini, fim, incluir_cfr_b)
    dataset.to_csv(saida / ARQUIVO_DATASET, index=False, encoding="utf-8", lineterminator="\n")

    metricas = ["freq_deploy_release", "lead_time_a_dias", "cfr_a", "tempo_recuperacao_horas"]
    if incluir_cfr_b:
        metricas.append("cfr_b")
    completos = dataset[metricas].notna().all(axis=1).sum()
    print(
        f"{len(dataset)} repositórios no dataset ({completos} com {', '.join(metricas)} preenchidos). "
        f"CFR (b): {'incluído' if incluir_cfr_b else 'fora (use --incluir-cfr-b depois da rotulagem)'}.\n"
        f"Salvo em {saida / ARQUIVO_DATASET}"
    )
    return dataset


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - dataset consolidado (uma linha por repositório)")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--saida", default=str(DADOS_PADRAO), help="pasta dos CSVs de entrada e do dataset.csv")
    ap.add_argument("--incluir-cfr-b", action="store_true",
                    help="inclui o CFR (b) de cfr_entrega_repos.csv (só depois da rotulagem da amostra-ouro)")
    args = ap.parse_args()

    ini, fim = parse_janela(args.inicio, args.fim)
    executar(ini, fim, Path(args.saida), args.incluir_cfr_b)


if __name__ == "__main__":
    main()
