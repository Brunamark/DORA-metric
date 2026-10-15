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


# --------------------------------------------------------------------------
# Resiliência: token inválido, cache corrompido e respostas que não são JSON
# --------------------------------------------------------------------------
import json  # noqa: E402

import pytest  # noqa: E402

from selecao_repos import ErroDeToken  # noqa: E402


class RespostaFalsa:
    def __init__(self, status, corpo=None, texto=None, headers=None):
        self.status_code = status
        self.headers = headers or {"X-RateLimit-Remaining": "4999"}
        self._corpo = corpo
        self.text = texto if texto is not None else json.dumps(corpo)
        self.content = self.text.encode()

    def json(self):
        if self._corpo is None:
            raise ValueError("não é JSON")
        return self._corpo


def cliente_com_respostas(tmp_path, *respostas):
    client = GitHubClient("token-de-teste", tmp_path)
    fila = list(respostas)
    client.session.get = lambda *a, **kw: fila.pop(0)
    return client


def test_token_invalido_interrompe_e_nao_vai_para_o_cache(tmp_path):
    client = cliente_com_respostas(tmp_path, RespostaFalsa(401, {"message": "Bad credentials"}))

    with pytest.raises(ErroDeToken):
        client.get("/repos/org/projeto/tags", {"page": 1})

    assert list(tmp_path.glob("*.json")) == []


def test_401_salvo_por_versao_antiga_e_consultado_de_novo(tmp_path):
    client = cliente_com_respostas(tmp_path, RespostaFalsa(200, [{"name": "v1"}]))
    url = API + "/repos/org/projeto/tags"
    client._arquivo_cache(url, {"page": 1}).write_text(
        '{"status": 401, "body": {"message": "Bad credentials"}, "link": null}', encoding="utf-8"
    )

    status, corpo, _ = client.get("/repos/org/projeto/tags", {"page": 1})

    assert (status, corpo) == (200, [{"name": "v1"}])
    assert client.chamadas == 1
    assert json.loads(client._arquivo_cache(url, {"page": 1}).read_text(encoding="utf-8"))["status"] == 200


def test_cache_corrompido_por_interrupcao_e_consultado_de_novo(tmp_path):
    client = cliente_com_respostas(tmp_path, RespostaFalsa(200, [1]))
    client._arquivo_cache(API + "/repos/org/projeto/tags", None).write_text('{"status": 20', encoding="utf-8")

    assert client.get("/repos/org/projeto/tags") == (200, [1], None)
    assert client.chamadas == 1


def test_gravacao_nao_deixa_arquivo_temporario(tmp_path):
    client = cliente_com_respostas(tmp_path, RespostaFalsa(200, [1]))

    client.get("/repos/org/projeto/tags")

    assert list(tmp_path.glob("*.tmp")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_resposta_que_nao_e_json_vira_mensagem(tmp_path):
    client = cliente_com_respostas(tmp_path, RespostaFalsa(404, None, texto="<html>Not Found</html>"))

    status, corpo, _ = client.get("/repos/org/projeto/tags")

    assert status == 404
    assert corpo == {"message": "<html>Not Found</html>"}
