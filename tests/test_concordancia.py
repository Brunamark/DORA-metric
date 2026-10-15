"""Kappa de Fleiss: casos conhecidos, interpretação de Landis & Koch e saídas."""

import math

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.inter_rater import fleiss_kappa

from concordancia import (
    calcular_kappas,
    interpretar_kappa,
    kappa_fleiss,
    main,
    tabela_markdown,
)
from dados_validacao import INTEGRANTES, preencher, rotulo_padrao, sortear_e_gravar
from validar_rotulos import carregar_rotulos

# Exemplo clássico da Wikipedia (Fleiss' kappa, Worked example): 10 itens, 14 avaliadores,
# 5 categorias. Cada linha conta quantos avaliadores escolheram cada categoria.
TABELA_WIKIPEDIA = np.array([
    [0, 0, 0, 0, 14],
    [0, 2, 6, 4, 2],
    [0, 0, 3, 5, 6],
    [0, 3, 9, 2, 0],
    [2, 2, 8, 1, 1],
    [7, 7, 0, 0, 0],
    [3, 2, 6, 3, 0],
    [2, 5, 3, 2, 2],
    [6, 5, 2, 1, 0],
    [0, 2, 2, 3, 7],
])


def avaliacoes_da_tabela(tabela: np.ndarray) -> np.ndarray:
    """Desfaz a tabela de contagens em rótulos individuais: itens x avaliadores."""
    return np.array([np.repeat(np.arange(len(linha)), linha) for linha in tabela])


# --------------------------------------------------------------------------
# kappa_fleiss
# --------------------------------------------------------------------------
def test_concordancia_total_da_kappa_1():
    avaliacoes = [["sim", "sim", "sim"], ["não", "não", "não"], ["incerto", "incerto", "incerto"], ["sim", "sim", "sim"]]

    assert kappa_fleiss(avaliacoes) == pytest.approx(1.0)


def test_exemplo_classico_de_fleiss_da_kappa_0_210():
    assert kappa_fleiss(avaliacoes_da_tabela(TABELA_WIKIPEDIA)) == pytest.approx(0.210, abs=0.001)


def test_o_exemplo_de_fleiss_confere_com_o_statsmodels_direto():
    direto = fleiss_kappa(TABELA_WIKIPEDIA, method="fleiss")

    assert kappa_fleiss(avaliacoes_da_tabela(TABELA_WIKIPEDIA)) == pytest.approx(direto)
    assert direto == pytest.approx(0.2099, abs=0.0001)


def test_a_ordem_dos_avaliadores_nao_muda_o_kappa():
    avaliacoes = avaliacoes_da_tabela(TABELA_WIKIPEDIA)
    embaralhadas = avaliacoes[:, np.random.RandomState(0).permutation(avaliacoes.shape[1])]

    assert kappa_fleiss(embaralhadas) == pytest.approx(kappa_fleiss(avaliacoes))


def test_aceita_rotulos_em_texto_ou_numeros():
    textos = [["a", "a", "b"], ["b", "b", "b"], ["a", "b", "a"]]
    numeros = [[0, 0, 1], [1, 1, 1], [0, 1, 0]]

    assert kappa_fleiss(textos) == pytest.approx(kappa_fleiss(numeros))


def test_discordancia_sistematica_da_kappa_negativo():
    avaliacoes = [["sim", "não", "sim"], ["não", "sim", "não"], ["sim", "não", "não"], ["não", "sim", "sim"]]

    assert kappa_fleiss(avaliacoes) < 0


def test_todos_sempre_na_mesma_categoria_e_indefinido():
    assert math.isnan(kappa_fleiss([["sim"] * 3 for _ in range(10)]))


@pytest.mark.parametrize("formato", [["sim", "não"], [["sim"], ["não"]], np.empty((0, 3))])
def test_entrada_com_formato_invalido_e_erro(formato):
    with pytest.raises(ValueError, match="itens|avaliadores|linha"):
        kappa_fleiss(formato)


# --------------------------------------------------------------------------
# Interpretação de Landis & Koch (1977)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(("kappa", "esperada"), [
    (-0.5, "pobre"),
    (-0.001, "pobre"),
    (0.0, "leve"),
    (0.20, "leve"),
    (0.21, "razoável"),
    (0.40, "razoável"),
    (0.41, "moderada"),
    (0.60, "moderada"),
    (0.61, "substancial"),
    (0.80, "substancial"),
    (0.81, "quase perfeita"),
    (1.0, "quase perfeita"),
])
def test_interpretacao_de_landis_e_koch(kappa, esperada):
    assert interpretar_kappa(kappa) == esperada


def test_o_kappa_de_fleiss_do_exemplo_classico_e_razoavel():
    assert interpretar_kappa(0.210) == "razoável"


def test_kappa_indefinido_nao_tem_interpretacao():
    assert interpretar_kappa(float("nan")) == "indefinida"
    assert interpretar_kappa(None) == "indefinida"


# --------------------------------------------------------------------------
# Três dimensões, CSV e Markdown
# --------------------------------------------------------------------------
@pytest.fixture
def pasta(tmp_path):
    sortear_e_gravar(tmp_path)
    for nome in INTEGRANTES:
        preencher(tmp_path, nome, rotulo_padrao)
    return tmp_path


def test_kappa_das_tres_dimensoes_com_concordancia_total(pasta):
    kappas = calcular_kappas(carregar_rotulos(pasta, INTEGRANTES)).set_index("dimensao")

    assert list(kappas.index) == ["tipo_projeto", "releases_reais", "corretiva"]
    assert kappas["kappa"].tolist() == [1.0, 1.0, 1.0]
    assert kappas["interpretacao"].tolist() == ["quase perfeita"] * 3
    assert kappas["n_itens"].tolist() == [8, 8, 40]  # repositórios, repositórios, releases
    assert kappas["n_avaliadores"].tolist() == [3, 3, 3]
    assert kappas["pct_itens_unanimes"].tolist() == [100.0, 100.0, 100.0]


def test_kappa_cai_quando_um_avaliador_discorda(pasta):
    def contrario(dimensao, repo, tag):
        valor = rotulo_padrao(dimensao, repo, tag)
        return {"sim": "não", "não": "sim"}.get(valor, valor) if dimensao == "corretiva" else valor

    preencher(pasta, "carla", contrario)

    kappas = calcular_kappas(carregar_rotulos(pasta, INTEGRANTES)).set_index("dimensao")

    assert kappas.loc["tipo_projeto", "kappa"] == 1.0
    assert kappas.loc["corretiva", "kappa"] < 0.2
    assert kappas.loc["corretiva", "pct_itens_unanimes"] == 0.0


def test_dimensao_sem_variacao_fica_indefinida_em_vez_de_quebrar(pasta):
    for nome in INTEGRANTES:
        preencher(pasta, nome, lambda d, r, t: "sim" if d == "corretiva" else rotulo_padrao(d, r, t))

    kappas = calcular_kappas(carregar_rotulos(pasta, INTEGRANTES)).set_index("dimensao")

    assert kappas.loc["corretiva", "kappa"] == ""
    assert kappas.loc["corretiva", "interpretacao"] == "indefinida"
    assert kappas.loc["corretiva", "pct_itens_unanimes"] == 100.0


def test_tabela_markdown_tem_uma_linha_por_dimensao_com_virgula_decimal():
    kappas = pd.DataFrame([
        {"dimensao": "tipo_projeto", "n_itens": 60, "n_avaliadores": 3, "n_categorias_usadas": 4,
         "pct_itens_unanimes": 71.7, "kappa": 0.6123, "interpretacao": "substancial"},
        {"dimensao": "corretiva", "n_itens": 300, "n_avaliadores": 3, "n_categorias_usadas": 1,
         "pct_itens_unanimes": 100.0, "kappa": "", "interpretacao": "indefinida"},
    ])

    linhas = tabela_markdown(kappas).splitlines()

    assert linhas[0].startswith("| Dimensão |") and linhas[1].startswith("|---|")
    assert linhas[2] == "| Tipo do projeto | 60 | 3 | 71,7 | 0,612 | substancial |"
    assert linhas[3] == "| Release corretiva | 300 | 3 | 100,0 | indefinido | indefinida |"


def test_cli_grava_kappa_csv_e_markdown(pasta, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["concordancia.py", "--integrantes", *INTEGRANTES, "--pasta", str(pasta)])

    main()

    kappa = pd.read_csv(pasta / "kappa.csv")
    assert list(kappa["dimensao"]) == ["tipo_projeto", "releases_reais", "corretiva"]
    assert list(kappa.columns) == ["dimensao", "n_itens", "n_avaliadores", "n_categorias_usadas",
                                   "pct_itens_unanimes", "kappa", "interpretacao"]
    assert "κ de Fleiss" in (pasta / "kappa.md").read_text(encoding="utf-8")
    assert "kappa.md" in capsys.readouterr().out


def test_cli_nao_calcula_com_planilha_incompleta(pasta, monkeypatch):
    preencher(pasta, "ana", lambda d, r, t: "" if d == "corretiva" else rotulo_padrao(d, r, t))
    monkeypatch.setattr("sys.argv", ["concordancia.py", "--integrantes", *INTEGRANTES, "--pasta", str(pasta)])

    with pytest.raises(SystemExit, match="kappa não calculado"):
        main()
    assert not (pasta / "kappa.csv").exists()
