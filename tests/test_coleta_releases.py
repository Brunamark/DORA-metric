from datetime import datetime, timezone

from coleta_releases import commits_entre, listar_releases, listar_tags, processar_repo

REPO = "org/projeto"
INI = datetime(2025, 10, 1, tzinfo=timezone.utc)
FIM = datetime(2026, 10, 1, 23, 59, 59, tzinfo=timezone.utc)


class ClienteFalso:
    """Simula GitHubClient.get: respostas por (caminho, página) e registro das chamadas."""

    def __init__(self, respostas: dict):
        self.respostas = respostas
        self.chamadas = []

    def get(self, path, params=None, enxugar=None):
        pagina = (params or {}).get("page", 1)
        self.chamadas.append((path, pagina))
        status, corpo, link = self.respostas.get((path, pagina), (404, {"message": "Not Found"}, None))
        if enxugar and status == 200:
            corpo = enxugar(corpo)
        return status, corpo, link


def release(tag, publicada_em, draft=False, prerelease=False):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": None if draft else publicada_em,
        "created_at": publicada_em,
    }


def commit(sha, data):
    return {"sha": sha, "commit": {"author": {"date": data}}, "files": ["diff enorme"]}


def compare(*commits):
    return 200, {"total_commits": len(commits), "commits": list(commits), "files": ["diff"]}, None


def link_proxima(pagina):
    return f'<https://api.github.com/x?page={pagina}>; rel="next"'


def caminho_compare(base, head):
    return f"/repos/{REPO}/compare/{base}...{head}"


def test_primeira_release_do_historico_e_ignorada():
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, [release("v1.0", "2026-01-10T00:00:00Z")], None),
    })

    resultado = processar_repo(cliente, REPO, INI, FIM)

    assert resultado["releases"][0]["status"] == "primeira_release"
    assert resultado["resumo"]["releases_calculadas"] == 0


def test_drafts_e_prereleases_ficam_fora_da_definicao_de_deploy():
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.1-rc1", "2026-03-10T00:00:00Z", prerelease=True),
            release("v1.2-draft", "2026-03-12T00:00:00Z", draft=True),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z")),
    })

    resultado = processar_repo(cliente, REPO, INI, FIM)
    status = {r["tag_name"]: r["status"] for r in resultado["releases"]}

    assert status == {
        "v1.1": "ok",
        "v1.1-rc1": "excluida_prerelease",
        "v1.2-draft": "excluida_draft",
        "v1.0": "primeira_release",
    }
    assert ("/repos/org/projeto/compare/v1.1-rc1...v1.1", 1) not in cliente.chamadas


def test_exemplo_da_issue_calcula_as_duas_variantes():
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(
            commit("a", "2026-03-02T00:00:00Z"),
            commit("b", "2026-03-10T00:00:00Z"),
            commit("c", "2026-03-14T00:00:00Z"),
        ),
    })

    resultado = processar_repo(cliente, REPO, INI, FIM)

    v1_1 = next(r for r in resultado["releases"] if r["tag_name"] == "v1.1")
    assert v1_1["lead_time_release_dias"] == 13
    assert [c["lead_time_dias"] for c in resultado["commits"]] == [13, 5, 1]
    assert resultado["resumo"]["lead_time_release_mediana_dias"] == 13
    assert resultado["resumo"]["lead_time_commit_mediana_dias"] == 5


def test_tag_404_pula_a_release_e_conta():
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
    })

    resultado = processar_repo(cliente, REPO, INI, FIM)

    assert resultado["releases"][0]["status"] == "tag_404"
    assert resultado["resumo"]["releases_404"] == 1
    assert resultado["resumo"]["lead_time_release_mediana_dias"] == ""


def test_release_sem_commits_novos_e_registrada_sem_lead_time():
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(),
    })

    resultado = processar_repo(cliente, REPO, INI, FIM)

    assert resultado["releases"][0]["status"] == "sem_commits"
    assert resultado["resumo"]["releases_sem_commits"] == 1
    assert resultado["commits"] == []


def test_release_anterior_a_janela_serve_de_base_mas_nao_entra_no_calculo():
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, [
            release("v2.0", "2025-10-05T00:00:00Z"),
            release("v1.9", "2025-09-20T00:00:00Z"),
            release("v1.8", "2025-09-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.9", "v2.0"), 1): compare(commit("a", "2025-10-01T00:00:00Z")),
    })

    resultado = processar_repo(cliente, REPO, INI, FIM)
    status = {r["tag_name"]: r["status"] for r in resultado["releases"]}

    assert status == {"v2.0": "ok", "v1.9": "fora_da_janela", "v1.8": "fora_da_janela"}
    assert resultado["resumo"]["releases_na_janela"] == 1


def test_compare_segue_a_paginacao_ate_o_fim():
    caminho = caminho_compare("v1.0", "v1.1")
    cliente = ClienteFalso({
        (caminho, 1): (200, {"total_commits": 3, "commits": [commit("a", "2026-03-02T00:00:00Z")]}, link_proxima(2)),
        (caminho, 2): (200, {"total_commits": 3, "commits": [commit("b", "2026-03-10T00:00:00Z")]}, link_proxima(3)),
        (caminho, 3): (200, {"total_commits": 3, "commits": [commit("c", "2026-03-14T00:00:00Z")]}, None),
    })

    status, commits = commits_entre(cliente, REPO, "v1.0", "v1.1")

    assert status == 200
    assert [c["sha"] for c in commits] == ["a", "b", "c"]


def test_compare_descarta_os_diffs_antes_do_cache():
    cliente = ClienteFalso({(caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z"))})

    _, commits = commits_entre(cliente, REPO, "v1.0", "v1.1")

    assert "files" not in commits[0]


def test_tags_com_barra_sao_codificadas_na_url():
    cliente = ClienteFalso({})

    commits_entre(cliente, REPO, "@scope/pkg@1.0.0", "@scope/pkg@1.1.0")

    assert cliente.chamadas[0][0] == f"/repos/{REPO}/compare/%40scope%2Fpkg%401.0.0...%40scope%2Fpkg%401.1.0"


def test_listagem_de_releases_pagina_ate_achar_a_anterior_da_janela():
    pagina_1 = [release(f"v2.{i}", "2026-05-01T00:00:00Z") for i in range(100)]
    pagina_2 = [release("v1.0", "2025-01-01T00:00:00Z")]
    cliente = ClienteFalso({
        (f"/repos/{REPO}/releases", 1): (200, pagina_1, link_proxima(2)),
        (f"/repos/{REPO}/releases", 2): (200, pagina_2, link_proxima(3)),
    })

    releases = listar_releases(cliente, REPO, INI)

    assert len(releases) == 101
    assert (f"/repos/{REPO}/releases", 3) not in cliente.chamadas


def test_listagem_de_tags_segue_a_paginacao():
    tag = lambda nome: {"name": nome, "commit": {"sha": nome}}
    cliente = ClienteFalso({
        (f"/repos/{REPO}/tags", 1): (200, [tag("v2")], link_proxima(2)),
        (f"/repos/{REPO}/tags", 2): (200, [tag("v1")], None),
    })

    assert [t["name"] for t in listar_tags(cliente, REPO)] == ["v2", "v1"]
