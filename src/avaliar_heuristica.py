#!/usr/bin/env python3
"""
Lab03S02 - avaliação da heurística de release corretiva contra a amostra-ouro (issue #10).

Compara cada versão da heurística (pareamento × critério, ver metricas.py) com o rótulo
de consenso da dimensão (iii) da amostra-ouro ("a release é corretiva?") e calcula
precisão, recall e F1 com sklearn.metrics.precision_recall_fscore_support.

Entradas:
  --consenso         rótulos da amostra-ouro, em qualquer um destes formatos (valores sim/não;
                     "incerto" ou vazio fica fora e é contado):
                       - consenso da issue #9 (src/consenso.py), formato longo: dimensao, repo,
                         tag, rotulo_consenso (só as linhas com dimensao = corretiva são usadas);
                       - planilha de rotulagem (src/amostra_ouro.py): repo, tag, corretiva;
                       - formato largo: full_name, tag_name e `corretiva_consenso` ou `corretiva`.
  --caracteristicas  src/data/releases_corretivas.csv (etapa `corretivas` do pipeline)

Saídas em --saida (padrão: validacao/):
  avaliacao_heuristica.csv  uma linha por versão: VP, FP, FN, VN, P, R, F1 (ordenado por F1)
  avaliacao_heuristica.md   a mesma tabela em Markdown, para o artigo e docs/heuristica_corretiva.md
  erros_heuristica.csv      falsos positivos e negativos de cada versão, com as características
                            da release (base do refinamento)

Uma predição indeterminada (critério sem dados suficientes) conta como "não corretiva" e
é contada na coluna `indeterminadas`.

Uso:
    python src/avaliar_heuristica.py
"""

import argparse
import csv
import sys
import unicodedata
from pathlib import Path

from metricas import CRITERIOS, PAREAMENTOS
from selecao_repos import DADOS_PADRAO, DIR_SRC, salvar_csv

DIR_VALIDACAO = DIR_SRC.parent / "validacao"
LIMIAR_F1 = 0.70
COLUNAS_ROTULO = ("corretiva_consenso", "corretiva")

CAMPOS_AVALIACAO = [
    "versao", "pareamento", "criterio", "n", "vp", "fp", "fn", "vn",
    "indeterminadas", "precisao", "recall", "f1",
]
CAMPOS_ERROS = [
    "versao", "erro", "full_name", "tag_name", "predecessora", "tipo_mudanca",
    "n_commits", "n_fix", "n_fix_amplo", "n_fix_deps", "notas_mencionam_correcao", "patch_recente_7d",
]


def normalizar_rotulo(valor: str | None) -> bool | None:
    """sim/não (com ou sem acento, maiúsculas, s/n, yes/no, true/false, 1/0) -> bool; resto -> None."""
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    if texto in {"sim", "s", "yes", "y", "true", "1"}:
        return True
    if texto in {"nao", "n", "no", "false", "0"}:
        return False
    return None


def prf_manual(y_true: list[bool], y_pred: list[bool]) -> tuple[float, float, float]:
    """Precisão, recall e F1 da classe positiva (zero quando o denominador é zero)."""
    vp = sum(t and p for t, p in zip(y_true, y_pred))
    fp = sum(p and not t for t, p in zip(y_true, y_pred))
    fn = sum(t and not p for t, p in zip(y_true, y_pred))
    precisao = vp / (vp + fp) if vp + fp else 0.0
    recall = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
    return precisao, recall, f1


def prf(y_true: list[bool], y_pred: list[bool]) -> tuple[float, float, float]:
    """Precisão, recall e F1 com sklearn (como pede o enunciado); sem sklearn, cálculo manual."""
    try:
        from sklearn.metrics import precision_recall_fscore_support
    except ImportError:  # pragma: no cover - o CI instala o scikit-learn
        return prf_manual(y_true, y_pred)
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", pos_label=True, zero_division=0
    )
    return float(p), float(r), float(f)


def ler_csv(caminho: Path) -> list[dict]:
    if not caminho.exists():
        sys.exit(f"{caminho} não existe.")
    with caminho.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


DIMENSAO_CORRETIVA = "corretiva"


def ler_consenso(linhas: list[dict], coluna: str | None = None) -> tuple[dict, int]:
    """(full_name, tag_name) -> bool, e o nº de rótulos descartados (incerto/vazio).
    Aceita o formato longo do consenso, a planilha de rotulagem e o formato largo."""
    if not linhas:
        return {}, 0
    if "dimensao" in linhas[0]:   # consenso.csv da issue #9: uma linha por (dimensão, release)
        linhas = [l for l in linhas if (l.get("dimensao") or "").strip() == DIMENSAO_CORRETIVA]
        coluna = coluna or "rotulo_consenso"
    linhas = [{**l, "full_name": l.get("full_name") or l.get("repo", ""),
               "tag_name": l.get("tag_name") or l.get("tag", "")} for l in linhas]
    if not linhas:
        return {}, 0
    if coluna is None:
        coluna = next((c for c in COLUNAS_ROTULO if c in linhas[0]), None)
        if coluna is None:
            sys.exit(f"O consenso precisa de uma coluna de rótulo: {' ou '.join(COLUNAS_ROTULO)}.")
    rotulos, descartados = {}, 0
    for linha in linhas:
        valor = normalizar_rotulo(linha.get(coluna))
        if valor is None:
            descartados += 1
        else:
            rotulos[(linha["full_name"], linha["tag_name"])] = valor
    return rotulos, descartados


def avaliar(rotulos: dict, caracteristicas: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Avalia todas as versões. Retorna (linhas da avaliação, erros, rótulos sem características)."""
    por_chave = {(c["full_name"], c["tag_name"], c["pareamento"]): c for c in caracteristicas}
    avaliacao, erros = [], []
    sem_caracteristicas = sum(
        1 for (fn, tag) in rotulos if all((fn, tag, p) not in por_chave for p in PAREAMENTOS)
    )
    for pareamento in PAREAMENTOS:
        for criterio in CRITERIOS:
            versao = f"{pareamento}/{criterio}"
            y_true, y_pred, indeterminadas = [], [], 0
            for (fn, tag), verdade in sorted(rotulos.items()):
                linha = por_chave.get((fn, tag, pareamento))
                if linha is None:
                    continue
                bruto = linha.get(f"corretiva_{criterio}", "")
                indeterminadas += bruto == ""
                previsto = bruto == "sim"
                y_true.append(verdade)
                y_pred.append(previsto)
                if previsto != verdade:
                    erros.append({
                        "versao": versao, "erro": "falso_positivo" if previsto else "falso_negativo",
                        **{campo: linha.get(campo, "") for campo in CAMPOS_ERROS if campo not in ("versao", "erro")},
                    })
            precisao, recall, f1 = prf(y_true, y_pred) if y_true else (0.0, 0.0, 0.0)
            avaliacao.append({
                "versao": versao, "pareamento": pareamento, "criterio": criterio, "n": len(y_true),
                "vp": sum(t and p for t, p in zip(y_true, y_pred)),
                "fp": sum(p and not t for t, p in zip(y_true, y_pred)),
                "fn": sum(t and not p for t, p in zip(y_true, y_pred)),
                "vn": sum(not t and not p for t, p in zip(y_true, y_pred)),
                "indeterminadas": indeterminadas,
                "precisao": round(precisao, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            })
    avaliacao.sort(key=lambda a: (-a["f1"], a["versao"]))
    return avaliacao, erros, sem_caracteristicas


def tabela_markdown(avaliacao: list[dict]) -> str:
    linhas = ["| Versão | n | VP | FP | FN | VN | Precisão | Recall | F1 |", "|---|---|---|---|---|---|---|---|---|"]
    for a in avaliacao:
        linhas.append(
            f"| {a['versao']} | {a['n']} | {a['vp']} | {a['fp']} | {a['fn']} | {a['vn']} "
            f"| {a['precisao']:.2f} | {a['recall']:.2f} | {a['f1']:.2f} |"
        )
    return "\n".join(linhas)


def executar(consenso: Path, caracteristicas: Path, saida: Path, coluna: str | None = None) -> list[dict]:
    rotulos, descartados = ler_consenso(ler_csv(consenso), coluna)
    avaliacao, erros, sem_carac = avaliar(rotulos, ler_csv(caracteristicas))
    saida.mkdir(parents=True, exist_ok=True)
    salvar_csv(saida / "avaliacao_heuristica.csv", CAMPOS_AVALIACAO, avaliacao)
    salvar_csv(saida / "erros_heuristica.csv", CAMPOS_ERROS, erros)
    (saida / "avaliacao_heuristica.md").write_text(tabela_markdown(avaliacao) + "\n", encoding="utf-8")

    print(tabela_markdown(avaliacao))
    print(f"\n{len(rotulos)} releases rotuladas ({descartados} rótulos incertos/vazios descartados; "
          f"{sem_carac} sem características em releases_corretivas.csv).")
    if avaliacao:
        melhor = avaliacao[0]
        situacao = "atinge" if melhor["f1"] >= LIMIAR_F1 else "NÃO atinge"
        print(f"Melhor versão: {melhor['versao']} (F1 = {melhor['f1']:.2f}), que {situacao} o mínimo de {LIMIAR_F1:.2f}.")
    print(f"Salvo em {saida}/ (avaliacao_heuristica.csv, avaliacao_heuristica.md, erros_heuristica.csv).")
    return avaliacao


def main() -> None:
    ap = argparse.ArgumentParser(description="Lab03S02 - P/R/F1 da heurística de release corretiva")
    ap.add_argument("--consenso", default=str(DIR_VALIDACAO / "consenso.csv"))
    ap.add_argument("--caracteristicas", default=str(DADOS_PADRAO / "releases_corretivas.csv"))
    ap.add_argument("--coluna", default=None, help=f"coluna do rótulo (padrão: {' ou '.join(COLUNAS_ROTULO)})")
    ap.add_argument("--saida", default=str(DIR_VALIDACAO))
    args = ap.parse_args()
    executar(Path(args.consenso), Path(args.caracteristicas), Path(args.saida), args.coluna)


if __name__ == "__main__":
    main()
