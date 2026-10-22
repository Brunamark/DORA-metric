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


# --------------------------------------------------------------------------
# CFR (b): versões, release corretiva e CFR de entrega (issue #10)
# --------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

from metricas import (  # noqa: E402
    CRITERIOS,
    ReleaseClassificada,
    ReleasePublicada,
    avaliar_criterio,
    caracteristicas_commits,
    cfr_entrega,
    eh_corretiva,
    parse_versao,
    patches_recentes,
    predecessoras,
    situacao_releases,
    tem_palavra_corretiva,
    tipo_mudanca,
)


@pytest.mark.parametrize("tag, prefixo, numeros, sufixo", [
    ("v1.2.3", "", (1, 2, 3, 0), ""),
    ("1.2.3", "", (1, 2, 3, 0), ""),
    ("release-1.2.3", "release-", (1, 2, 3, 0), ""),
    ("pkg@1.2.3", "pkg@", (1, 2, 3, 0), ""),
    ("@scope/pkg@1.2.3", "@scope/pkg@", (1, 2, 3, 0), ""),
    ("1.2.3-beta.1", "", (1, 2, 3, 0), "-beta.1"),
    ("v2.0.0-rc.2", "", (2, 0, 0, 0), "-rc.2"),
    ("v1.30.4+k3s1", "", (1, 30, 4, 0), "+k3s1"),
    ("v25.8.10.43-lts", "", (25, 8, 10, 43), "-lts"),
    ("v2.3", "", (2, 3, 0, 0), ""),
    ("1.13b", "", (1, 13, 0, 0), "b"),
    ("1.2.3.post1", "", (1, 2, 3, 0), ".post1"),            # PEP 440
    ("App2-V1.2.3", "app2-", (1, 2, 3, 0), ""),
])
def test_parse_versao_aceita_prefixos_e_sufixos(tag, prefixo, numeros, sufixo):
    v = parse_versao(tag)

    assert (v.prefixo, v.numeros, v.sufixo) == (prefixo, numeros, sufixo)
    assert not v.calendario


@pytest.mark.parametrize("tag", ["cli-latest", "release-2026-08-21", "v8", "nightly", "", None])
def test_tag_que_nao_segue_semver_nao_tem_versao(tag):
    assert parse_versao(tag) is None


def test_versao_por_calendario_e_marcada():
    assert parse_versao("2025.10.1").calendario


@pytest.mark.parametrize("anterior, atual, esperado", [
    ("v2.3.0", "v2.3.1", "patch"),
    ("v2.4.0", "v2.5.0", "minor"),
    ("v1.9.9", "v2.0.0", "major"),
    ("v25.8.10.43-lts", "v25.8.10.50-lts", "patch"),
    ("v1.30.4+k3s1", "v1.30.4+k3s2", "sufixo"),
    ("v1.2.3", "1.2.3", "igual"),
    ("v25.9.3", "v25.8.10", "regressao"),
    ("pkg-a@1.0.0", "pkg-b@1.0.1", None),      # pacotes diferentes
    ("2025.10.1", "2025.10.2", None),          # calendário
    ("cli-latest", "v1.0.0", None),
])
def test_tipo_mudanca(anterior, atual, esperado):
    assert tipo_mudanca(parse_versao(anterior), parse_versao(atual)) == esperado


@pytest.mark.parametrize("titulo, esperado", [
    ("fix: crash ao abrir arquivo", True),
    ("fix(parser): trata vírgula", True),
    ("Hotfix for login", True),
    ('Revert "feat: novo cache"', True),
    ("FIX typo", True),
    ("prefix the logger", False),
    ("add fixture for tests", False),
    ("fixes #123", False),                      # flexão: só na variante ampla
    ("feat: nova tela", False),
    (None, False),
])
def test_palavra_corretiva_v1_e_palavra_inteira(titulo, esperado):
    assert tem_palavra_corretiva(titulo) is esperado


def test_variante_ampla_aceita_flexoes():
    assert tem_palavra_corretiva("fixes #123", ampla=True)
    assert tem_palavra_corretiva("bugfix: x", ampla=True)
    assert tem_palavra_corretiva("reverted the change", ampla=True)


def test_caracteristicas_separam_merges_e_dependencias():
    c = caracteristicas_commits([
        "fix: crash",
        "fix(deps): update dependency foo to v2",
        "Merge pull request #12 from org/fix-crash",
        "feat: tela",
    ])

    assert (c.n_commits, c.n_merges, c.n_fix, c.n_fix_deps, c.n_fix_amplo) == (4, 1, 3, 1, 2)


# --- eh_corretiva -------------------------------------------------------------
def test_exemplo_do_enunciado_so_patch_com_fix_e_corretiva():
    assert eh_corretiva("v2.3.1", "v2.3.0", ["fix: crash ao abrir arquivo"]) is True


def test_minor_nao_e_corretiva_no_criterio_v1():
    assert eh_corretiva("v2.5.0", "v2.4.0", ["fix: crash", "feat: x"]) is False


def test_patch_sem_commit_de_correcao_nao_e_corretiva_no_v1():
    assert eh_corretiva("v2.3.1", "v2.3.0", ["docs: readme"]) is False


def test_criterios_ou_e_isolados():
    assert eh_corretiva("v2.3.1", "v2.3.0", ["docs: readme"], criterio="semver_ou_mensagem") is True
    assert eh_corretiva("v2.5.0", "v2.4.0", ["fix: x"], criterio="semver_ou_mensagem") is True
    assert eh_corretiva("v2.3.1", "v2.3.0", ["docs"], criterio="so_semver") is True
    assert eh_corretiva("v2.5.0", "v2.4.0", ["fix: x"], criterio="so_mensagem") is True


def test_criterio_sem_deps_ignora_patch_so_de_dependencia():
    msgs = ["fix(deps): update dependency foo to v2"]

    assert eh_corretiva("v1.0.1", "v1.0.0", msgs) is True
    assert eh_corretiva("v1.0.1", "v1.0.0", msgs, criterio="semver_e_mensagem_sem_deps") is False


def test_criterio_maioria_fix():
    assert eh_corretiva("v1.0.1", "v1.0.0", ["fix: a", "fixes b", "docs"], criterio="semver_e_maioria_fix") is True
    assert eh_corretiva("v1.0.1", "v1.0.0", ["fix: a", "feat: b", "feat: c"], criterio="semver_e_maioria_fix") is False
    assert eh_corretiva("v1.0.1", "v1.0.0", ["Merge branch x"], criterio="semver_e_maioria_fix") is False


def test_tag_sem_versao_deixa_criterio_de_versao_indeterminado():
    assert eh_corretiva("cli-latest", "v1.0.0", ["fix: x"]) is None          # e: indeterminado
    assert eh_corretiva("cli-latest", "v1.0.0", ["fix: x"], criterio="semver_ou_mensagem") is True
    assert eh_corretiva("cli-latest", "v1.0.0", ["docs"], criterio="semver_ou_mensagem") is None


def test_commits_desconhecidos_deixam_criterio_de_mensagem_indeterminado():
    assert eh_corretiva("v1.0.1", "v1.0.0", None) is None
    assert eh_corretiva("v1.1.0", "v1.0.0", None) is False                   # minor já decide


def test_primeira_release_nao_e_corretiva():
    assert eh_corretiva("v1.0.0", None, []) is False


def test_criterio_desconhecido_falha_explicitamente():
    with pytest.raises(ValueError):
        avaliar_criterio("patch", None, "inventado")


def test_todos_os_criterios_aceitam_entradas_desconhecidas():
    for criterio in CRITERIOS:
        assert avaliar_criterio(None, None, criterio) is None


# --- predecessoras ------------------------------------------------------------
def pub(tag, d, h=0):
    return ReleasePublicada(tag, datetime(2026, 5, d, h, tzinfo=timezone.utc))


def test_predecessora_cronologica_e_a_publicada_logo_antes():
    rels = [pub("v25.9.3", 2), pub("v25.8.10", 3), pub("v25.9.4", 4)]

    assert predecessoras(rels, "cronologico") == {"v25.9.3": None, "v25.8.10": "v25.9.3", "v25.9.4": "v25.8.10"}


def test_predecessora_por_linha_ignora_linhas_paralelas():
    rels = [pub("v25.8.9", 1), pub("v25.9.3", 2), pub("v25.8.10", 3), pub("v25.9.4", 4), pub("v25.10.1", 5)]

    assert predecessoras(rels) == {
        "v25.8.9": None,
        "v25.9.3": "v25.8.9",       # nova minor: compara com a maior versão abaixo
        "v25.8.10": "v25.8.9",
        "v25.9.4": "v25.9.3",
        "v25.10.1": "v25.9.4",
    }


def test_predecessora_por_linha_separa_pacotes_de_monorepo():
    rels = [pub("core@0.3.4", 1), pub("openai@0.4.1", 2), pub("core@0.3.5", 3), pub("openai@0.4.2", 4)]

    pred = predecessoras(rels)

    assert pred["core@0.3.5"] == "core@0.3.4"
    assert pred["openai@0.4.2"] == "openai@0.4.1"
    assert pred["openai@0.4.1"] is None


def test_predecessora_por_linha_com_mesmo_numero_e_sufixo_diferente():
    assert predecessoras([pub("v1.30.4+k3s1", 1), pub("v1.30.4+k3s2", 2)])["v1.30.4+k3s2"] == "v1.30.4+k3s1"


def test_tag_sem_versao_usa_a_predecessora_cronologica():
    assert predecessoras([pub("v1.0.0", 1), pub("cli-latest", 2)])["cli-latest"] == "v1.0.0"


def test_pareamento_desconhecido_falha_explicitamente():
    with pytest.raises(ValueError):
        predecessoras([], "aleatorio")


# --- cfr_entrega --------------------------------------------------------------
FIM = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)


def rel(tag, data, pred=None, corretiva=False):
    return ReleaseClassificada(tag, data, pred, corretiva)


def d(mes, dia, h=0):
    return datetime(2026, mes, dia, h, tzinfo=timezone.utc)


def test_exemplos_do_enunciado():
    releases = [
        rel("v2.3.0", d(5, 10)),
        rel("v2.3.1", d(5, 12), "v2.3.0", corretiva=True),
        rel("v2.4.0", d(6, 1), "v2.3.1"),
        rel("v2.5.0", d(6, 20), "v2.4.0"),
    ]

    situacao = situacao_releases(releases, FIM)

    assert situacao["v2.3.0"] == "falhou"
    assert situacao["v2.4.0"] == "nao_falhou"
    assert cfr_entrega(releases, FIM) == (0.25, 4, 1, 0)


def test_corretiva_no_7o_dia_conta_e_no_8o_nao():
    no_prazo = [rel("v1.0.0", d(5, 1)), rel("v1.0.1", d(5, 8), "v1.0.0", corretiva=True)]
    fora = [rel("v1.0.0", d(5, 1)), rel("v1.0.1", d(5, 9), "v1.0.0", corretiva=True)]
    quase = [rel("v1.0.0", d(5, 1)), rel("v1.0.1", d(5, 8) + timedelta(seconds=1), "v1.0.0", corretiva=True)]

    assert situacao_releases(no_prazo, FIM)["v1.0.0"] == "falhou"
    assert situacao_releases(fora, FIM)["v1.0.0"] == "nao_falhou"
    assert situacao_releases(quase, FIM)["v1.0.0"] == "nao_falhou"


def test_release_nos_ultimos_7_dias_da_janela_e_censurada():
    releases = [rel("v1.0.0", d(9, 20)), rel("v1.1.0", FIM - timedelta(days=7)), rel("v1.2.0", d(9, 24))]

    situacao = situacao_releases(releases, FIM)

    assert situacao["v1.0.0"] == "nao_falhou"
    assert situacao["v1.1.0"] == "nao_falhou"        # exatamente 7 dias antes do fim: dá para observar
    assert situacao["v1.2.0"] == "censurada"
    assert cfr_entrega(releases, FIM) == (0.0, 2, 0, 1)


def test_repositorio_com_uma_unica_release():
    assert cfr_entrega([rel("v1.0.0", d(5, 1))], FIM) == (0.0, 1, 0, 0)


def test_repositorio_so_com_releases_censuradas_nao_tem_cfr():
    assert cfr_entrega([rel("v1.0.0", d(9, 29))], FIM) == (None, 0, 0, 1)


def test_corretiva_de_outra_release_nao_faz_a_anterior_falhar():
    # A v1.1.1 corrige a v1.1.0 (sua predecessora), não a v1.0.0, mesmo publicada no prazo das duas
    releases = [
        rel("v1.0.0", d(5, 1)),
        rel("v1.1.0", d(5, 2), "v1.0.0"),
        rel("v1.1.1", d(5, 3), "v1.1.0", corretiva=True),
    ]

    situacao = situacao_releases(releases, FIM)

    assert situacao["v1.0.0"] == "nao_falhou"
    assert situacao["v1.1.0"] == "falhou"


def test_corretiva_indeterminada_nao_conta_como_falha():
    releases = [rel("v1.0.0", d(5, 1)), rel("v1.0.1", d(5, 2), "v1.0.0", corretiva=None)]

    assert situacao_releases(releases, FIM)["v1.0.0"] == "nao_falhou"


def test_releases_fora_da_janela_servem_de_contexto_mas_nao_contam():
    ini = d(5, 1)
    releases = [
        rel("v0.9.0", d(4, 28)),                                   # antes da janela
        rel("v0.9.1", d(5, 2), "v0.9.0", corretiva=True),          # dentro: corrige uma de fora
        rel("v1.0.0", FIM + timedelta(days=1), "v0.9.1"),          # depois da janela
    ]

    assert cfr_entrega(releases, FIM, inicio_janela=ini) == (0.0, 1, 0, 0)


# --- regra do relatório (docs/src/metricas.py) ---------------------------------
def test_patch_recente_marca_o_patch_da_mesma_linha_em_ate_7_dias():
    rels = [pub("v1.2.0", 1), pub("v1.2.1", 8), pub("v1.2.2", 16), pub("v1.3.0", 17)]

    assert patches_recentes(rels) == {"v1.2.0": False, "v1.2.1": True, "v1.2.2": False, "v1.3.0": False}


def test_patch_recente_respeita_prefixo_e_major_minor():
    rels = [pub("pkg-a@1.0.0", 1), pub("pkg-b@1.0.1", 2), pub("v2.0.0", 3), pub("v2.1.1", 4)]

    assert not any(patches_recentes(rels).values())


def test_patch_recente_aceita_mesmo_dia_e_versao_sem_patch():
    rels = [pub("v3.1", 5, 1), pub("v3.1.1", 5, 2), pub("sem-versao", 5, 3)]

    assert patches_recentes(rels) == {"v3.1": False, "v3.1.1": True, "sem-versao": False}


def test_criterio_do_relatorio_le_so_os_extras():
    assert avaliar_criterio("minor", None, "relatorio_patch_7d", {"patch_recente_7d": True}) is True
    assert avaliar_criterio("patch", None, "relatorio_patch_7d", {"patch_recente_7d": False}) is False
    assert avaliar_criterio("patch", None, "relatorio_patch_7d") is None
