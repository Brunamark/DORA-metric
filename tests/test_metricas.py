from datetime import datetime, timezone

import pytest

from conftest import dia
from metricas import (
    lead_time_commit,
    lead_time_release,
    mediana_lead_time_commit,
    mediana_lead_time_release,
)


def test_exemplo_v1_1_variante_release_da_13_dias(release_v1_1):
    assert lead_time_release(*release_v1_1) == 13


def test_exemplo_v1_1_variante_commit_da_13_5_1_dias(release_v1_1):
    assert lead_time_commit(*release_v1_1) == [13, 5, 1]


def test_variante_release_usa_o_commit_mais_antigo_independente_da_ordem(data_v1_1, commits_v1_1):
    fora_de_ordem = list(reversed(commits_v1_1))

    assert lead_time_release(data_v1_1, fora_de_ordem) == 13


def test_lead_time_considera_fracoes_de_dia():
    release = datetime(2026, 3, 15, 12, tzinfo=timezone.utc)
    commit = datetime(2026, 3, 15, 0, tzinfo=timezone.utc)

    assert lead_time_release(release, [commit]) == pytest.approx(0.5)


def test_release_sem_commits_novos_nao_tem_lead_time_por_release(data_v1_1):
    assert lead_time_release(data_v1_1, []) is None


def test_release_sem_commits_novos_nao_gera_lead_time_por_commit(data_v1_1):
    assert lead_time_commit(data_v1_1, []) == []


def test_mediana_por_release_ignora_releases_sem_commits(release_v1_1):
    releases = [
        release_v1_1,                  # 13 dias
        (dia(3, 20), []),              # sem commits novos
        (dia(4, 1), [dia(3, 25)]),     # 7 dias
    ]

    assert mediana_lead_time_release(releases) == 10


def test_mediana_por_commit_junta_os_commits_de_todas_as_releases(release_v1_1):
    releases = [
        release_v1_1,                  # 13, 5, 1
        (dia(4, 1), [dia(3, 25)]),     # 7
    ]

    assert mediana_lead_time_commit(releases) == 6


def test_repositorio_sem_releases_calculaveis_nao_tem_mediana():
    assert mediana_lead_time_release([]) is None
    assert mediana_lead_time_commit([]) is None


def test_commit_antigo_esquecido_domina_a_variante_release_mas_nao_a_de_commit(release_com_commit_esquecido):
    por_release = lead_time_release(*release_com_commit_esquecido)
    por_commit = mediana_lead_time_commit([release_com_commit_esquecido])

    assert por_release == 90
    assert por_commit == 2.5
