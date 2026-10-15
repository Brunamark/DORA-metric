from selecao_repos import API, GitHubClient


def test_versao_do_cache_muda_a_chave_e_sem_versao_a_chave_antiga_se_mantem(tmp_path):
    client = GitHubClient("token-de-teste", tmp_path)
    url, params = API + "/repos/org/projeto/compare/v1.0...v1.1", {"per_page": 100, "page": 1}

    sem_versao = client._arquivo_cache(url, params)
    com_versao = client._arquivo_cache(url, params, "compare-v2-mensagem")

    assert sem_versao != com_versao
    assert sem_versao == client._arquivo_cache(url, params, None)


def test_resposta_em_cache_nao_chama_a_api(tmp_path):
    client = GitHubClient("token-de-teste", tmp_path)
    url = API + "/repos/org/projeto/releases"
    client._arquivo_cache(url, {"page": 1}, "v2").write_text(
        '{"status": 200, "body": [1, 2], "link": null}', encoding="utf-8"
    )

    assert client.get("/repos/org/projeto/releases", {"page": 1}, versao_cache="v2") == (200, [1, 2], None)
    assert (client.chamadas, client.cache_hits) == (0, 1)

