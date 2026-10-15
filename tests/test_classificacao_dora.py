"""Classificação DORA (Lab03S02): cortes fixos do enunciado, testados em cada limite de faixa."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import dia
from metricas import (
    CFR,
    FREQUENCIA_DEPLOY,
    LEAD_TIME,
    METRICAS_DORA,
    TEMPO_RECUPERACAO,
    classificacao_geral,
    classificar,
    frequencia_deploy,
    nota,
)


# --------------------------------------------------------------------------
# frequencia_deploy
# --------------------------------------------------------------------------
def test_frequencia_deploy_divide_releases_pelas_semanas_da_janela():
    ini = dia(1, 1)

    assert frequencia_deploy(14, ini, ini + timedelta(weeks=2)) == pytest.approx(7)


def test_janela_de_365_dias_tem_cerca_de_52_1_semanas():
    ini, fim = dia(1, 1, 2026), dia(1, 1, 2027)

    assert frequencia_deploy(521, ini, fim) == pytest.approx(521 / 52.142857, rel=1e-6)


def test_frequencia_deploy_sem_releases_e_zero():
    assert frequencia_deploy(0, dia(1, 1), dia(12, 31)) == 0


def test_frequencia_deploy_aceita_datas_sem_hora():
    assert frequencia_deploy(2, datetime(2026, 1, 1).date(), datetime(2026, 1, 15).date()) == pytest.approx(1)


def test_frequencia_deploy_com_janela_invertida_ou_vazia_e_erro():
    with pytest.raises(ValueError):
        frequencia_deploy(5, dia(2, 1), dia(1, 1))
    with pytest.raises(ValueError):
        frequencia_deploy(5, dia(1, 1), dia(1, 1))


def test_frequencia_deploy_com_releases_negativas_e_erro():
    with pytest.raises(ValueError):
        frequencia_deploy(-1, dia(1, 1), dia(12, 31))


# --------------------------------------------------------------------------
# classificar: limites de cada faixa
# --------------------------------------------------------------------------
UMA_POR_MES = 12 / (365 / 7)  # 12 releases em 365 dias, em releases por semana

LIMITES = [
    # deployment frequency (releases por semana): Elite >= 7; High >= 1; Medium >= 1/mês; Low < 1/mês
    (FREQUENCIA_DEPLOY, 7, "Elite"),
    (FREQUENCIA_DEPLOY, 7.01, "Elite"),
    (FREQUENCIA_DEPLOY, 6.99, "High"),
    (FREQUENCIA_DEPLOY, 1, "High"),
    (FREQUENCIA_DEPLOY, 0.99, "Medium"),
    (FREQUENCIA_DEPLOY, UMA_POR_MES, "Medium"),
    (FREQUENCIA_DEPLOY, UMA_POR_MES - 0.01, "Low"),
    (FREQUENCIA_DEPLOY, 0, "Low"),
    # lead time (dias): Elite < 1; High 1 a < 7; Medium 7 a < 30; Low >= 30
    (LEAD_TIME, 0, "Elite"),
    (LEAD_TIME, 0.99, "Elite"),
    (LEAD_TIME, 1, "High"),
    (LEAD_TIME, 6.99, "High"),
    (LEAD_TIME, 7, "Medium"),
    (LEAD_TIME, 29.99, "Medium"),
    (LEAD_TIME, 30, "Low"),
    (LEAD_TIME, 400, "Low"),
    # CFR (proporção): Elite <= 15%; High > 15% e <= 30%; Medium > 30% e <= 45%; Low > 45%
    (CFR, 0, "Elite"),
    (CFR, 0.15, "Elite"),
    (CFR, 0.1501, "High"),
    (CFR, 0.30, "High"),
    (CFR, 0.3001, "Medium"),
    (CFR, 0.45, "Medium"),
    (CFR, 0.4501, "Low"),
    (CFR, 1, "Low"),
    # tempo de recuperação (horas): Elite < 1; High 1 a < 24; Medium 24 a < 168; Low >= 168
    (TEMPO_RECUPERACAO, 0.5, "Elite"),
    (TEMPO_RECUPERACAO, 0.99, "Elite"),
    (TEMPO_RECUPERACAO, 1, "High"),
    (TEMPO_RECUPERACAO, 23.99, "High"),
    (TEMPO_RECUPERACAO, 24, "Medium"),
    (TEMPO_RECUPERACAO, 167.99, "Medium"),
    (TEMPO_RECUPERACAO, 168, "Low"),
    (TEMPO_RECUPERACAO, 1000, "Low"),
]


@pytest.mark.parametrize(("metrica", "valor", "esperada"), LIMITES)
def test_classificar_nos_limites_de_cada_faixa(metrica, valor, esperada):
    assert classificar(metrica, valor) == esperada


def test_exemplos_do_card_exatamente_7_por_semana_1_dia_e_15_por_cento():
    assert classificar(FREQUENCIA_DEPLOY, 7) == "Elite"
    assert classificar(LEAD_TIME, 1) == "High"
    assert classificar(CFR, 0.15) == "Elite"


def test_uma_release_por_mes_vem_da_frequencia_calculada_pela_janela():
    """12 releases numa janela de 365 dias são exatamente 1 por mês: Medium, não Low."""
    freq = frequencia_deploy(12, dia(1, 1, 2026), dia(1, 1, 2027))

    assert classificar(FREQUENCIA_DEPLOY, freq) == "Medium"


def test_sete_releases_por_semana_vindas_da_janela_sao_elite():
    ini = dia(1, 1)
    freq = frequencia_deploy(7 * 52, ini, ini + timedelta(weeks=52))

    assert classificar(FREQUENCIA_DEPLOY, freq) == "Elite"


def test_valor_ausente_nao_tem_categoria():
    for metrica in METRICAS_DORA:
        assert classificar(metrica, None) is None


def test_metrica_desconhecida_e_erro():
    with pytest.raises(ValueError, match="desconhecida"):
        classificar("mttr", 1)


@pytest.mark.parametrize("metrica", METRICAS_DORA)
def test_valor_negativo_e_erro(metrica):
    with pytest.raises(ValueError, match="negativa"):
        classificar(metrica, -0.1)


# --------------------------------------------------------------------------
# nota e classificacao_geral
# --------------------------------------------------------------------------
def test_notas_das_categorias():
    assert [nota(c) for c in ("Elite", "High", "Medium", "Low")] == [4, 3, 2, 1]


def test_nota_de_categoria_desconhecida_e_erro():
    with pytest.raises(ValueError):
        nota("Gold")


def test_exemplo_do_enunciado_4_3_3_1_e_high():
    assert classificacao_geral((4, 3, 3, 1)) == "High"


def test_mediana_com_meio_ponto_e_arredondada_para_baixo():
    assert classificacao_geral((4, 4, 1, 1)) == "Medium"  # mediana 2,5 -> 2
    assert classificacao_geral((4, 3, 2, 1)) == "Medium"  # mediana 2,5 -> 2
    assert classificacao_geral((4, 4, 4, 3)) == "Elite"  # mediana 4
    assert classificacao_geral((1, 1, 1, 1)) == "Low"


def test_ordem_das_notas_nao_importa():
    assert classificacao_geral((1, 3, 4, 3)) == classificacao_geral((4, 3, 3, 1))


def test_classificacao_geral_aceita_qualquer_iteravel():
    assert classificacao_geral(n for n in (4, 3, 3, 1)) == "High"


def test_classificacao_geral_exige_quatro_notas():
    with pytest.raises(ValueError, match="quatro|4"):
        classificacao_geral((4, 3, 3))


@pytest.mark.parametrize("notas", [(0, 3, 3, 1), (5, 3, 3, 1), (4, 3, 3, 2.5)])
def test_classificacao_geral_rejeita_notas_fora_de_1_a_4(notas):
    with pytest.raises(ValueError, match="1, 2, 3 ou 4"):
        classificacao_geral(notas)


def test_do_valor_a_classificacao_geral_de_um_repositorio():
    """Fluxo completo: valores das quatro métricas -> categorias -> notas -> categoria geral."""
    valores = {FREQUENCIA_DEPLOY: 8, LEAD_TIME: 3, CFR: 0.2, TEMPO_RECUPERACAO: 200}
    categorias = [classificar(m, v) for m, v in valores.items()]

    assert categorias == ["Elite", "High", "High", "Low"]
    assert classificacao_geral([nota(c) for c in categorias]) == "High"
