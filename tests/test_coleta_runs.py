from datetime import datetime, timedelta, timezone

import pytest

from coleta_runs import (
    TETO_RESULTADOS,
    coletar_runs,
    dividir_fatia,
    executar,
    fatias_mensais,
    formatar_created,
    processar_repo,
    run_da_api,
)
from conftest import REPO, ClienteRunsFalso, run_api


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def runs_exemplo_rq04_api():
    """success 09:00 -> failure 10:00 -> failure 10:30 -> success 11:15 (terminou 11:20)."""
    return [
        run_api(1, "success", "2026-03-10T09:00:00Z"),
        run_api(2, "failure", "2026-03-10T10:00:00Z"),
        run_api(3, "failure", "2026-03-10T10:30:00Z"),
        run_api(4, "success", "2026-03-10T11:15:00Z", fim="2026-03-10T11:20:00Z"),
    ]


def runs_em_sequencia(n, inicio, passo):
    """n runs de sucesso a partir de `inicio`, um a cada `passo`."""
    return [
        run_api(i, "success", (inicio + i * passo).strftime("%Y-%m-%dT%H:%M:%SZ"))
        for i in range(n)
    ]


# --------------------------------------------------------------------------
# Divisão da janela em meses e em pedaços menores
# --------------------------------------------------------------------------
def test_janela_e_dividida_em_meses_sem_buracos_nem_sobreposicao(janela):
    fatias = fatias_mensais(*janela)

    assert len(fatias) == 13      # out/2025 a set/2026 + o dia 01/10/2026
    assert fatias[0] == (utc(2025, 10, 1), utc(2025, 10, 31, 23, 59, 59))
    assert fatias[4] == (utc(2026, 2, 1), utc(2026, 2, 28, 23, 59, 59))
    assert fatias[-1] == (utc(2026, 10, 1), utc(2026, 10, 1, 23, 59, 59))
    for (_, fim_anterior), (inicio, _) in zip(fatias, fatias[1:]):
        assert inicio - fim_anterior == timedelta(seconds=1)


def test_janela_comecando_no_meio_do_mes_corta_a_primeira_fatia():
    fatias = fatias_mensais(utc(2026, 1, 15), utc(2026, 2, 10, 23, 59, 59))

    assert fatias == [
        (utc(2026, 1, 15), utc(2026, 1, 31, 23, 59, 59)),
        (utc(2026, 2, 1), utc(2026, 2, 10, 23, 59, 59)),
    ]


def test_filtro_created_usa_datas_para_dias_inteiros_e_horario_no_resto():
    assert formatar_created(utc(2026, 3, 1), utc(2026, 3, 31, 23, 59, 59)) == "2026-03-01..2026-03-31"
    assert formatar_created(utc(2026, 3, 1), utc(2026, 3, 1, 11, 59, 59)) == (
        "2026-03-01T00:00:00Z..2026-03-01T11:59:59Z"
    )


def test_fatia_de_varios_dias_e_dividida_por_dias():
    primeira, segunda = dividir_fatia(utc(2026, 3, 1), utc(2026, 3, 31, 23, 59, 59))

    assert primeira == (utc(2026, 3, 1), utc(2026, 3, 15, 23, 59, 59))
    assert segunda == (utc(2026, 3, 16), utc(2026, 3, 31, 23, 59, 59))


def test_fatia_de_um_dia_e_dividida_por_horario():
    primeira, segunda = dividir_fatia(utc(2026, 3, 1), utc(2026, 3, 1, 23, 59, 59))

    assert primeira == (utc(2026, 3, 1), utc(2026, 3, 1, 11, 59, 59))
    assert segunda == (utc(2026, 3, 1, 12), utc(2026, 3, 1, 23, 59, 59))


def test_fatia_menor_que_uma_hora_nao_e_dividida():
    assert dividir_fatia(utc(2026, 3, 1, 10), utc(2026, 3, 1, 10, 30)) is None


# --------------------------------------------------------------------------
# Coleta: paginação, teto de 1.000 e filtros
# --------------------------------------------------------------------------
def test_coleta_segue_a_paginacao_dentro_do_mes(janela):
    base = runs_em_sequencia(250, utc(2026, 3, 1), timedelta(minutes=10))
    api = ClienteRunsFalso(base)

    status, runs, fatias = coletar_runs(api, REPO, "main", *janela)

    assert status == 200
    assert len(runs) == 250
    paginas_de_marco = [p for _, created, p in api.chamadas if created == "2026-03-01..2026-03-31"]
    assert max(paginas_de_marco) == 3
    assert not any(f["dividida"] for f in fatias)


def test_mes_que_atinge_o_teto_e_dividido_ate_caber(janela):
    # 1.500 runs em março: a consulta do mês só enxergaria 1.000
    base = runs_em_sequencia(1500, utc(2026, 3, 1), timedelta(minutes=25))
    api = ClienteRunsFalso(base)

    status, runs, fatias = coletar_runs(api, REPO, "main", *janela)

    assert status == 200
    assert len(runs) == 1500
    marco = next(f for f in fatias if f["inicio"].startswith("2026-03-01") and f["fim"].startswith("2026-03-31"))
    assert marco["dividida"] and marco["total_count"] == 1500
    assert not any(f["no_teto"] for f in fatias)


def test_mes_que_atinge_o_teto_gera_aviso_no_terminal(janela, capsys):
    base = runs_em_sequencia(1500, utc(2026, 3, 1), timedelta(minutes=25))

    coletar_runs(ClienteRunsFalso(base), REPO, "main", *janela)

    avisos = [linha for linha in capsys.readouterr().out.splitlines() if "aviso:" in linha]
    assert len(avisos) == 1
    assert "created=2026-03-01..2026-03-31" in avisos[0]
    assert "total_count=1500" in avisos[0]


def test_mes_abaixo_do_teto_nao_gera_aviso(janela, capsys):
    base = runs_em_sequencia(999, utc(2026, 3, 1), timedelta(minutes=40))

    coletar_runs(ClienteRunsFalso(base), REPO, "main", *janela)

    assert "aviso:" not in capsys.readouterr().out


def test_fatia_que_nao_da_para_dividir_avisa_que_fica_incompleta(capsys):
    base = runs_em_sequencia(1200, utc(2026, 3, 1, 10), timedelta(seconds=1))

    processar_repo(ClienteRunsFalso(base), REPO, "main", utc(2026, 3, 1, 10), utc(2026, 3, 1, 10, 20))

    saida = capsys.readouterr().out
    assert "continua no teto (total_count=1200)" in saida


def test_fatia_que_nao_da_para_dividir_fica_marcada_no_teto():
    # 1.200 runs em 20 minutos: a fatia é menor que 1 h, não divide mais e a API só mostra 1.000
    base = runs_em_sequencia(1200, utc(2026, 3, 1, 10), timedelta(seconds=1))
    api = ClienteRunsFalso(base)
    ini, fim = utc(2026, 3, 1, 10), utc(2026, 3, 1, 10, 20)

    resultado = processar_repo(api, REPO, "main", ini, fim)

    assert resultado["resumo"]["fatias_no_teto"] == 1
    assert resultado["fatias"][0]["total_count"] == 1200
    assert resultado["resumo"]["runs_coletados"] == TETO_RESULTADOS


def test_filtro_com_horario_recusado_pela_api_marca_o_dia_no_teto_sem_derrubar_o_repo():
    # 1.200 runs num único dia: a divisão por horário é recusada (422) e o dia fica incompleto
    base = runs_em_sequencia(1200, utc(2026, 3, 10), timedelta(seconds=30))
    api = ClienteRunsFalso(base, erros={"2026-03-10T00:00:00Z..2026-03-10T11:59:59Z": 422})

    resultado = processar_repo(api, REPO, "main", utc(2026, 3, 10), utc(2026, 3, 10, 23, 59, 59))

    assert resultado["resumo"]["status_runs"] == "ok"
    assert resultado["resumo"]["fatias_no_teto"] == 1
    assert resultado["resumo"]["runs_coletados"] == TETO_RESULTADOS


def test_nao_pede_alem_da_decima_pagina():
    base = runs_em_sequencia(2000, utc(2026, 3, 1, 10), timedelta(milliseconds=500))
    api = ClienteRunsFalso(base)

    coletar_runs(api, REPO, "main", utc(2026, 3, 1, 10), utc(2026, 3, 1, 10, 30))

    assert max(p for _, _, p in api.chamadas) == TETO_RESULTADOS // 100


def test_runs_de_outro_branch_evento_ou_fora_da_janela_ficam_de_fora(janela):
    base = [
        run_api(1, "success", "2026-03-10T09:00:00Z"),
        run_api(2, "success", "2026-03-10T10:00:00Z", branch="develop"),
        run_api(3, "success", "2026-03-10T11:00:00Z", event="schedule"),
        run_api(4, "success", "2025-09-30T23:00:00Z"),      # antes da janela
    ]
    api = ClienteRunsFalso(base)

    _, runs, _ = coletar_runs(api, REPO, "main", *janela)

    assert [r["id"] for r in runs] == [1]


def test_cache_guarda_so_os_campos_usados(janela):
    api = ClienteRunsFalso([run_api(1, "success", "2026-03-10T09:00:00Z")])

    _, runs, _ = coletar_runs(api, REPO, "main", *janela)

    assert "head_commit" not in runs[0]
    assert runs[0]["run_started_at"] == "2026-03-10T09:00:00Z"


def test_erro_da_api_numa_fatia_mantem_o_repositorio_no_resumo(janela):
    api = ClienteRunsFalso(runs_exemplo_rq04_api(), erros={"2026-03-01..2026-03-31": 403})

    resultado = processar_repo(api, REPO, "main", *janela)

    assert resultado["resumo"]["status_runs"] == "erro_http_403"
    assert resultado["resumo"]["cfr_a"] == ""
    assert resultado["runs"] == []


# --------------------------------------------------------------------------
# Métricas calculadas a partir da coleta
# --------------------------------------------------------------------------
def test_conversao_usa_created_at_quando_run_started_at_vem_vazio():
    run = run_da_api(run_api(1, "failure", "2026-03-10T10:00:00Z", iniciado=False))

    assert run.iniciado_em is None
    assert run.criado_em == utc(2026, 3, 10, 10)


def test_exemplo_do_enunciado_vira_cfr_e_recuperacao_no_resumo(janela):
    base = runs_exemplo_rq04_api() + [run_api(5, "cancelled", "2026-03-10T12:00:00Z")]
    api = ClienteRunsFalso(base)

    resultado = processar_repo(api, REPO, "main", *janela)

    resumo = resultado["resumo"]
    assert (resumo["runs_coletados"], resumo["runs_sucesso"], resumo["runs_falha"], resumo["runs_ignorados"]) == (5, 2, 2, 1)
    assert resumo["cfr_a"] == 0.5
    assert resumo["tempo_recuperacao_mediana_horas"] == pytest.approx(80 / 60, abs=1e-4)
    assert (resumo["episodios"], resumo["episodios_censurados"], resumo["proporcao_censurados"]) == (1, 0, 0)
    assert resultado["episodios"][0]["duracao_horas"] == pytest.approx(1.3333)
    assert [r["classe"] for r in resultado["runs"]] == ["sucesso", "falha", "falha", "sucesso", "ignorado"]


def test_falha_nunca_recuperada_aparece_como_censurada_no_resumo(janela):
    base = [
        run_api(1, "success", "2026-03-10T09:00:00Z"),
        run_api(2, "failure", "2026-03-10T10:00:00Z"),
    ]
    api = ClienteRunsFalso(base)

    resultado = processar_repo(api, REPO, "main", *janela)

    resumo = resultado["resumo"]
    assert (resumo["episodios_censurados"], resumo["proporcao_censurados"]) == (1, 1)
    assert resumo["tempo_recuperacao_mediana_horas"] == ""
    assert resultado["episodios"][0]["censurado"] is True
    assert resultado["episodios"][0]["fim"] == ""


def test_executar_grava_os_quatro_csvs(janela, tmp_path):
    api = _com_contadores(ClienteRunsFalso(runs_exemplo_rq04_api()))

    resumos = executar(api, *janela, [{"full_name": REPO, "default_branch": "main"}], tmp_path)

    assert resumos[0]["cfr_a"] == 0.5
    for nome in ("runs.csv", "episodios.csv", "runs_fatias.csv", "workflow_runs_repos.csv"):
        assert (tmp_path / nome).exists()
    assert len((tmp_path / "runs.csv").read_text(encoding="utf-8").splitlines()) == 5


def test_executar_grava_cada_repositorio_assim_que_termina(janela, tmp_path):
    """Os runs de um repositório vão para o arquivo parcial antes do próximo começar."""
    api = _com_contadores(ClienteRunsFalso(runs_exemplo_rq04_api()))
    linhas_antes_do_segundo = []
    get_original = api.get

    def get(path, params=None, **kw):
        if "outro/repo" in path and not linhas_antes_do_segundo:
            parcial = (tmp_path / "runs.csv.parcial").read_text(encoding="utf-8").splitlines()
            linhas_antes_do_segundo.append(len(parcial))
        return get_original(path.replace("outro/repo", REPO), params, **kw)

    api.get = get
    repos = [{"full_name": REPO, "default_branch": "main"}, {"full_name": "outro/repo", "default_branch": "main"}]

    executar(api, *janela, repos, tmp_path)

    assert linhas_antes_do_segundo == [5]          # cabeçalho + 4 runs do primeiro repositório
    assert len((tmp_path / "runs.csv").read_text(encoding="utf-8").splitlines()) == 9
    assert not list(tmp_path.glob("*.parcial"))


def test_interrupcao_no_meio_mantem_os_csvs_da_execucao_anterior(janela, tmp_path):
    for nome in ("runs.csv", "episodios.csv", "runs_fatias.csv"):
        (tmp_path / nome).write_text("execucao anterior\n", encoding="utf-8")
    api = _com_contadores(ClienteRunsFalso(runs_exemplo_rq04_api()))
    get_original = api.get

    def get(path, params=None, **kw):
        if "outro/repo" in path:
            raise KeyboardInterrupt
        return get_original(path, params, **kw)

    api.get = get
    repos = [{"full_name": REPO, "default_branch": "main"}, {"full_name": "outro/repo", "default_branch": "main"}]

    with pytest.raises(KeyboardInterrupt):
        executar(api, *janela, repos, tmp_path)

    for nome in ("runs.csv", "episodios.csv", "runs_fatias.csv"):
        assert (tmp_path / nome).read_text(encoding="utf-8") == "execucao anterior\n"


def _com_contadores(api):
    """executar() imprime client.chamadas e client.cache_hits ao final."""

    class Envelope:
        chamadas = 0
        cache_hits = 0

        def get(self, *a, **kw):
            return api.get(*a, **kw)

    return Envelope()
