from datetime import datetime, timezone

import pytest

from conftest import dia, hora, workflow_run
from metricas import (
    cfr_runs,
    classificar_conclusao,
    episodios_falha,
    lead_time_commit,
    lead_time_release,
    mediana_lead_time_commit,
    mediana_lead_time_release,
    proporcao_censurados,
    tempo_recuperacao,
)

CONCLUSOES_IGNORADAS = ["cancelled", "skipped", "neutral", "action_required", "stale", None, ""]


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


# --------------------------------------------------------------------------
# Classificação dos runs pela conclusion
# --------------------------------------------------------------------------
def test_success_conta_como_sucesso():
    assert classificar_conclusao("success") == "sucesso"


@pytest.mark.parametrize("conclusao", ["failure", "timed_out", "startup_failure"])
def test_failure_timed_out_e_startup_failure_contam_como_falha(conclusao):
    assert classificar_conclusao(conclusao) == "falha"


@pytest.mark.parametrize("conclusao", CONCLUSOES_IGNORADAS)
def test_demais_conclusoes_sao_ignoradas(conclusao):
    assert classificar_conclusao(conclusao) is None


# --------------------------------------------------------------------------
# CFR (a): falhas / (falhas + sucessos), todos os workflows juntos
# --------------------------------------------------------------------------
def test_cfr_conta_falhas_sobre_runs_validos_e_ignora_cancelados():
    runs = [
        workflow_run(1, "success", hora(9)),
        workflow_run(2, "success", hora(10)),
        workflow_run(3, "success", hora(11)),
        workflow_run(4, "failure", hora(12)),
        workflow_run(5, "timed_out", hora(13)),
        workflow_run(6, "cancelled", hora(14)),
        workflow_run(7, "cancelled", hora(15)),
    ]

    assert cfr_runs(runs) == pytest.approx(2 / 5)


def test_cfr_junta_todos_os_workflows():
    runs = [
        workflow_run(1, "failure", hora(9), workflow_id=1),
        workflow_run(2, "success", hora(9), workflow_id=2),
        workflow_run(3, "success", hora(10), workflow_id=2),
        workflow_run(4, "startup_failure", hora(11), workflow_id=3),
    ]

    assert cfr_runs(runs) == 0.5


def test_cfr_sem_runs_validos_nao_existe():
    assert cfr_runs([]) is None
    assert cfr_runs([workflow_run(1, "cancelled", hora(9)), workflow_run(2, "skipped", hora(10))]) is None


# --------------------------------------------------------------------------
# Episódios de falha e tempo de recuperação (RQ 04)
# --------------------------------------------------------------------------
def test_exemplo_do_enunciado_da_1h20(runs_exemplo_rq04):
    episodios, _ = episodios_falha(runs_exemplo_rq04)

    assert len(episodios) == 1
    episodio = episodios[0]
    assert (episodio.inicio, episodio.fim) == (hora(10), hora(11, 20))
    assert episodio.n_falhas == 2
    assert (episodio.run_inicio, episodio.run_fim) == (2, 4)
    assert episodio.duracao_horas == pytest.approx(80 / 60)
    assert tempo_recuperacao(episodios) == pytest.approx(80 / 60)


def test_falha_nunca_recuperada_e_censurada():
    runs = [
        workflow_run(1, "success", hora(9)),
        workflow_run(2, "failure", hora(10)),
        workflow_run(3, "failure", hora(11)),
    ]

    episodios, _ = episodios_falha(runs)

    assert len(episodios) == 1
    assert episodios[0].censurado
    assert episodios[0].duracao_horas is None
    assert tempo_recuperacao(episodios) is None
    assert proporcao_censurados(episodios) == 1


def test_censurado_fica_fora_da_mediana_mas_entra_na_proporcao():
    runs = [
        workflow_run(1, "success", hora(9)),
        workflow_run(2, "failure", hora(10)),
        workflow_run(3, "success", hora(11), fim=hora(12)),   # episódio de 2 h
        workflow_run(4, "failure", hora(13)),                 # nunca recuperado
    ]

    episodios, _ = episodios_falha(runs)

    assert tempo_recuperacao(episodios) == 2
    assert proporcao_censurados(episodios) == 0.5


def test_run_cancelled_nao_fecha_episodio():
    runs = [
        workflow_run(1, "success", hora(9)),
        workflow_run(2, "failure", hora(10)),
        workflow_run(3, "cancelled", hora(11)),
    ]

    episodios, _ = episodios_falha(runs)

    assert episodios[0].censurado


@pytest.mark.parametrize("conclusao", CONCLUSOES_IGNORADAS)
def test_conclusoes_ignoradas_nao_mudam_cfr_nem_episodios(runs_exemplo_rq04, conclusao):
    com_ignorados = runs_exemplo_rq04 + [
        workflow_run(10, conclusao, hora(9, 30)),     # entre o sucesso e a primeira falha
        workflow_run(11, conclusao, hora(10, 45)),    # dentro do episódio
        workflow_run(12, conclusao, hora(12)),        # depois da recuperação
    ]

    assert cfr_runs(com_ignorados) == cfr_runs(runs_exemplo_rq04)
    assert episodios_falha(com_ignorados) == episodios_falha(runs_exemplo_rq04)


def test_workflow_unico_com_dois_episodios_usa_a_mediana():
    runs = [
        workflow_run(1, "success", hora(8)),
        workflow_run(2, "failure", hora(9)),
        workflow_run(3, "success", hora(9, 55), fim=hora(10)),    # 1 h
        workflow_run(4, "failure", hora(11)),
        workflow_run(5, "success", hora(13, 50), fim=hora(14)),   # 3 h
    ]

    episodios, _ = episodios_falha(runs)

    assert [e.duracao_horas for e in episodios] == [1, 3]
    assert tempo_recuperacao(episodios) == 2


def test_sucesso_de_outro_workflow_nao_fecha_o_episodio():
    runs = [
        workflow_run(1, "success", hora(8), workflow_id=1),
        workflow_run(2, "failure", hora(9), workflow_id=1),
        workflow_run(3, "success", hora(9, 30), workflow_id=2),   # outro workflow
        workflow_run(4, "success", hora(10, 55), fim=hora(11), workflow_id=1),
    ]

    episodios, _ = episodios_falha(runs)

    assert len(episodios) == 1
    assert episodios[0].workflow_id == 1
    assert episodios[0].duracao_horas == 2


def test_varios_workflows_sao_calculados_separados_e_agregados_pela_mediana():
    runs = [
        # workflow 1 (CI): episódio de 1 h
        workflow_run(1, "success", hora(8), workflow_id=1),
        workflow_run(2, "failure", hora(9), workflow_id=1),
        workflow_run(3, "success", hora(9, 55), fim=hora(10), workflow_id=1),
        # workflow 2 (lint), intercalado: episódios de 2 h e 6 h
        workflow_run(4, "success", hora(8, 30), workflow_id=2),
        workflow_run(5, "failure", hora(9, 30), workflow_id=2),
        workflow_run(6, "success", hora(11, 25), fim=hora(11, 30), workflow_id=2),
        workflow_run(7, "timed_out", hora(12), workflow_id=2),
        workflow_run(8, "success", hora(17, 55), fim=hora(18), workflow_id=2),
    ]

    episodios, _ = episodios_falha(runs)

    assert sorted((e.workflow_id, e.duracao_horas) for e in episodios) == [(1, 1), (2, 2), (2, 6)]
    assert tempo_recuperacao(episodios) == 2


def test_runs_fora_de_ordem_dao_o_mesmo_resultado(runs_exemplo_rq04):
    assert episodios_falha(list(reversed(runs_exemplo_rq04))) == episodios_falha(runs_exemplo_rq04)


def test_falhas_antes_do_primeiro_sucesso_nao_abrem_episodio():
    runs = [
        workflow_run(1, "failure", hora(9)),
        workflow_run(2, "failure", hora(10)),
        workflow_run(3, "success", hora(11)),
    ]

    episodios, sem_sucesso_anterior = episodios_falha(runs)

    assert episodios == []
    assert sem_sucesso_anterior == 1


def test_falhas_sem_sucesso_anterior_sao_contadas_por_workflow():
    runs = [
        workflow_run(1, "failure", hora(9), workflow_id=1),
        workflow_run(2, "failure", hora(9), workflow_id=2),
        workflow_run(3, "success", hora(10), workflow_id=3),
    ]

    _, sem_sucesso_anterior = episodios_falha(runs)

    assert sem_sucesso_anterior == 2


def test_inicio_usa_created_at_quando_run_started_at_vem_vazio():
    runs = [
        workflow_run(1, "success", hora(9)),
        workflow_run(2, "failure", hora(10), iniciado=False),
        workflow_run(3, "success", hora(10, 55), fim=hora(11)),
    ]

    episodios, _ = episodios_falha(runs)

    assert episodios[0].inicio == hora(10)


def test_repositorio_sem_episodios_nao_tem_recuperacao_nem_proporcao():
    runs = [workflow_run(1, "success", hora(9)), workflow_run(2, "success", hora(10))]

    episodios, sem_sucesso_anterior = episodios_falha(runs)

    assert (episodios, sem_sucesso_anterior) == ([], 0)
    assert tempo_recuperacao(episodios) is None
    assert proporcao_censurados(episodios) is None
