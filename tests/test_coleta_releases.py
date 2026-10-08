from coleta_releases import commits_entre, listar_releases, listar_tags, processar_repo
from conftest import (
    REPO,
    caminho_compare,
    caminho_releases,
    caminho_tags,
    commit,
    compare,
    link_proxima,
    release,
)


def status_por_tag(resultado):
    return {r["tag_name"]: r["status"] for r in resultado["releases"]}


# --------------------------------------------------------------------------
# Definição de deploy e escolha da release anterior
# --------------------------------------------------------------------------
def test_repositorio_com_uma_unica_release_nao_tem_lead_time(cliente, janela):
    api = cliente({(caminho_releases(), 1): (200, [release("v1.0", "2026-01-10T00:00:00Z")], None)})

    resultado = processar_repo(api, REPO, *janela)

    assert status_por_tag(resultado) == {"v1.0": "primeira_release"}
    assert resultado["resumo"]["releases_calculadas"] == 0
    assert resultado["resumo"]["lead_time_release_mediana_dias"] == ""


def test_drafts_e_prereleases_ficam_fora_da_definicao_de_deploy(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.1-rc1", "2026-03-10T00:00:00Z", prerelease=True),
            release("v1.2-draft", "2026-03-12T00:00:00Z", draft=True),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z")),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert status_por_tag(resultado) == {
        "v1.1": "ok",
        "v1.1-rc1": "excluida_prerelease",
        "v1.2-draft": "excluida_draft",
        "v1.0": "primeira_release",
    }
    assert (caminho_compare("v1.1-rc1", "v1.1"), 1) not in api.chamadas


def test_release_anterior_a_janela_serve_de_base_mas_nao_entra_no_calculo(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v2.0", "2025-10-05T00:00:00Z"),
            release("v1.9", "2025-09-20T00:00:00Z"),
            release("v1.8", "2025-09-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.9", "v2.0"), 1): compare(commit("a", "2025-10-01T00:00:00Z")),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert status_por_tag(resultado) == {"v2.0": "ok", "v1.9": "fora_da_janela", "v1.8": "fora_da_janela"}
    assert resultado["resumo"]["releases_na_janela"] == 1


# --------------------------------------------------------------------------
# Lead time calculado a partir da coleta
# --------------------------------------------------------------------------
def test_exemplo_da_issue_calcula_as_duas_variantes(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(
            commit("a", "2026-03-02T00:00:00Z"),
            commit("b", "2026-03-10T00:00:00Z"),
            commit("c", "2026-03-14T00:00:00Z"),
        ),
    })

    resultado = processar_repo(api, REPO, *janela)

    v1_1 = next(r for r in resultado["releases"] if r["tag_name"] == "v1.1")
    assert v1_1["lead_time_release_dias"] == 13
    assert [c["lead_time_dias"] for c in resultado["commits"]] == [13, 5, 1]
    assert resultado["resumo"]["lead_time_release_mediana_dias"] == 13
    assert resultado["resumo"]["lead_time_commit_mediana_dias"] == 5


def test_release_sem_commits_novos_e_registrada_sem_lead_time(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert status_por_tag(resultado)["v1.1"] == "sem_commits"
    assert resultado["resumo"]["releases_sem_commits"] == 1
    assert resultado["commits"] == []


def test_commit_com_data_posterior_a_release_e_contado_como_lead_time_negativo(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-16T00:00:00Z")),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert resultado["commits"][0]["lead_time_dias"] == -1
    assert resultado["resumo"]["commits_lead_time_negativo"] == 1


# --------------------------------------------------------------------------
# Erros da API ficam registrados nos CSVs
# --------------------------------------------------------------------------
def test_tag_404_pula_a_release_e_conta(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({(caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None)})

    resultado = processar_repo(api, REPO, *janela)

    assert status_por_tag(resultado)["v1.1"] == "tag_404"
    assert resultado["resumo"]["releases_404"] == 1
    assert resultado["resumo"]["lead_time_release_mediana_dias"] == ""


def test_outro_erro_no_compare_pula_a_release_e_conta_separado_do_404(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): (500, None, None),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert status_por_tag(resultado)["v1.1"] == "erro_http_500"
    assert resultado["resumo"]["releases_erro"] == 1
    assert resultado["resumo"]["releases_404"] == 0


def test_erro_ao_listar_releases_mantem_o_repositorio_no_resumo(cliente, janela):
    api = cliente({(caminho_releases(), 1): (403, {"message": "Forbidden"}, None)})

    resultado = processar_repo(api, REPO, *janela)

    assert resultado["resumo"]["full_name"] == REPO
    assert resultado["resumo"]["status_releases"] == "erro_http_403"
    assert resultado["releases"] == []


def test_erro_ao_listar_tags_fica_registrado_no_resumo(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_tags(), 1): (500, None, None),
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z")),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert resultado["resumo"]["status_tags"] == "erro_http_500"
    assert resultado["resumo"]["releases_calculadas"] == 1


def test_compare_com_commits_faltando_fica_marcado(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z"), total=300),
    })

    resultado = processar_repo(api, REPO, *janela)

    v1_1 = next(r for r in resultado["releases"] if r["tag_name"] == "v1.1")
    assert (v1_1["n_commits"], v1_1["total_commits_api"]) == (1, 300)
    assert resultado["resumo"]["releases_commits_incompletos"] == 1


# --------------------------------------------------------------------------
# Paginação e chamadas à API
# --------------------------------------------------------------------------
def test_compare_segue_a_paginacao_ate_o_fim(cliente):
    caminho = caminho_compare("v1.0", "v1.1")
    api = cliente({
        (caminho, 1): (200, {"total_commits": 3, "commits": [commit("a", "2026-03-02T00:00:00Z")]}, link_proxima(2)),
        (caminho, 2): (200, {"total_commits": 3, "commits": [commit("b", "2026-03-10T00:00:00Z")]}, link_proxima(3)),
        (caminho, 3): (200, {"total_commits": 3, "commits": [commit("c", "2026-03-14T00:00:00Z")]}, None),
    })

    status, commits, total = commits_entre(api, REPO, "v1.0", "v1.1")

    assert status == 200
    assert [c["sha"] for c in commits] == ["a", "b", "c"]
    assert total == 3


def test_compare_descarta_os_diffs_antes_do_cache(cliente):
    api = cliente({(caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z"))})

    _, commits, _ = commits_entre(api, REPO, "v1.0", "v1.1")

    assert "files" not in commits[0]


def test_tags_com_barra_sao_codificadas_na_url(cliente):
    api = cliente({})

    commits_entre(api, REPO, "@scope/pkg@1.0.0", "@scope/pkg@1.1.0")

    assert api.chamadas[0][0] == f"/repos/{REPO}/compare/%40scope%2Fpkg%401.0.0...%40scope%2Fpkg%401.1.0"


def test_listagem_de_releases_pagina_ate_achar_a_anterior_da_janela(cliente, janela):
    pagina_1 = [release(f"v2.{i}", "2026-05-01T00:00:00Z") for i in range(100)]
    pagina_2 = [release("v1.0", "2025-01-01T00:00:00Z")]
    api = cliente({
        (caminho_releases(), 1): (200, pagina_1, link_proxima(2)),
        (caminho_releases(), 2): (200, pagina_2, link_proxima(3)),
    })

    status, releases = listar_releases(api, REPO, janela[0])

    assert status == 200
    assert len(releases) == 101
    assert (caminho_releases(), 3) not in api.chamadas


def test_listagem_de_tags_segue_a_paginacao(cliente):
    def tag(nome):
        return {"name": nome, "commit": {"sha": nome}}

    api = cliente({
        (caminho_tags(), 1): (200, [tag("v2")], link_proxima(2)),
        (caminho_tags(), 2): (200, [tag("v1")], None),
    })

    status, tags = listar_tags(api, REPO)

    assert status == 200
    assert [t["name"] for t in tags] == ["v2", "v1"]
