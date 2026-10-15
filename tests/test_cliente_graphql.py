"""GitHubClient.graphql(): mesmo cache, rate limit e backoff do get(), mais os erros da GraphQL,
que chegam com HTTP 200 e o campo `errors`."""

import json

import pytest
import requests

from selecao_repos import API, API_GRAPHQL, ErroDeToken, GitHubClient

AGORA = 1_000_000
CONSULTA = "query($owner: String!) { repository(owner: $owner, name: \"projeto\") { id } }"
VARIAVEIS = {"owner": "org"}


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


def ok(dados=None):
    return RespostaFalsa(200, {"data": dados or {"repository": {"id": "R_1"}}})


def com_erros(*tipos, headers=None):
    corpo = {"data": None, "errors": [{"type": t, "message": t.lower()} for t in tipos]}
    return RespostaFalsa(200, corpo, headers=headers)


def cliente_graphql(tmp_path, *respostas):
    """Cliente cuja sessão devolve as respostas do POST na ordem; uma exceção na fila é
    lançada. As requisições enviadas ficam em client.enviadas."""
    client = GitHubClient("token-de-teste", tmp_path)
    fila = list(respostas)
    client.enviadas = []

    def responder(url, json=None, **kw):
        client.enviadas.append((url, json))
        item = fila.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    client.session.post = responder
    return client


@pytest.fixture
def esperas(monkeypatch):
    """Relógio parado em AGORA e time.sleep sem dormir: devolve a lista de esperas pedidas."""
    pedidas = []
    monkeypatch.setattr("selecao_repos.time.time", lambda: AGORA)
    monkeypatch.setattr("selecao_repos.time.sleep", pedidas.append)
    return pedidas


# --------------------------------------------------------------------------
# Requisição e cache
# --------------------------------------------------------------------------
def test_envia_query_e_variaveis_por_post(tmp_path):
    client = cliente_graphql(tmp_path, ok())

    status, corpo = client.graphql(CONSULTA, VARIAVEIS)

    assert (status, corpo) == (200, {"data": {"repository": {"id": "R_1"}}})
    assert client.enviadas == [(API_GRAPHQL, {"query": CONSULTA, "variables": VARIAVEIS})]


def test_resposta_em_cache_nao_chama_a_api_de_novo(tmp_path):
    client = cliente_graphql(tmp_path, ok())

    primeira = client.graphql(CONSULTA, VARIAVEIS)
    segunda = client.graphql(CONSULTA, VARIAVEIS)

    assert primeira == segunda
    assert (client.chamadas, client.cache_hits) == (1, 1)


def test_retomada_le_o_cache_gravado_por_outra_execucao(tmp_path):
    cliente_graphql(tmp_path, ok()).graphql(CONSULTA, VARIAVEIS)

    retomada = cliente_graphql(tmp_path)
    retomada.graphql(CONSULTA, VARIAVEIS)

    assert (retomada.chamadas, retomada.cache_hits) == (0, 1)


def test_variaveis_diferentes_tem_chaves_de_cache_diferentes(tmp_path):
    client = cliente_graphql(tmp_path, ok(), ok({"repository": {"id": "R_2"}}))

    client.graphql(CONSULTA, {"owner": "org"})
    _, corpo = client.graphql(CONSULTA, {"owner": "outra"})

    assert corpo["data"]["repository"]["id"] == "R_2"
    assert client.chamadas == 2


def test_chave_do_graphql_nao_colide_com_a_do_get(tmp_path):
    client = GitHubClient("token-de-teste", tmp_path)
    payload = {"query": CONSULTA, "variables": VARIAVEIS}

    assert client._arquivo_cache(API_GRAPHQL, payload) != client._arquivo_cache(API + "/graphql", None)


def test_versao_do_cache_muda_a_chave(tmp_path):
    client = cliente_graphql(tmp_path, ok(), ok())

    client.graphql(CONSULTA, VARIAVEIS)
    client.graphql(CONSULTA, VARIAVEIS, versao_cache="v2")

    assert client.chamadas == 2


# --------------------------------------------------------------------------
# Erros da GraphQL (HTTP 200 com o campo errors)
# --------------------------------------------------------------------------
def test_rate_limited_espera_o_reset_repete_e_nao_vai_para_o_cache(tmp_path, esperas):
    sem_cota = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(AGORA + 100)}
    client = cliente_graphql(tmp_path, com_erros("RATE_LIMITED", headers=sem_cota), ok())

    status, corpo = client.graphql(CONSULTA, VARIAVEIS)

    assert (status, "errors" in corpo) == (200, False)
    assert esperas == [102]
    salvo = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert "errors" not in salvo["body"]


def test_not_found_vai_para_o_cache_e_nao_e_repetido(tmp_path):
    client = cliente_graphql(tmp_path, com_erros("NOT_FOUND"))

    client.graphql(CONSULTA, VARIAVEIS)
    _, corpo = client.graphql(CONSULTA, VARIAVEIS)

    assert corpo["errors"][0]["type"] == "NOT_FOUND"
    assert (client.chamadas, client.cache_hits) == (1, 1)


def test_outros_erros_sao_devolvidos_mas_nao_vao_para_o_cache(tmp_path):
    client = cliente_graphql(tmp_path, com_erros("INTERNAL"), ok())

    _, primeira = client.graphql(CONSULTA, VARIAVEIS)
    _, segunda = client.graphql(CONSULTA, VARIAVEIS)

    assert primeira["errors"][0]["type"] == "INTERNAL"
    assert "errors" not in segunda
    assert client.chamadas == 2


def test_not_found_junto_de_outro_erro_nao_vai_para_o_cache(tmp_path):
    client = cliente_graphql(tmp_path, com_erros("NOT_FOUND", "INTERNAL"))

    client.graphql(CONSULTA, VARIAVEIS)

    assert list(tmp_path.glob("*.json")) == []


# --------------------------------------------------------------------------
# Token, rate limit HTTP e backoff (mesmo comportamento do get)
# --------------------------------------------------------------------------
def test_token_invalido_interrompe_e_nao_vai_para_o_cache(tmp_path):
    client = cliente_graphql(tmp_path, RespostaFalsa(401, {"message": "Bad credentials"}))

    with pytest.raises(ErroDeToken):
        client.graphql(CONSULTA, VARIAVEIS)

    assert list(tmp_path.glob("*.json")) == []


def test_rate_limit_secundario_respeita_retry_after(tmp_path, esperas):
    limitado = RespostaFalsa(403, {"message": "secondary rate limit"}, headers={"Retry-After": "30"})
    client = cliente_graphql(tmp_path, limitado, ok())

    client.graphql(CONSULTA, VARIAVEIS)

    assert esperas == [31]


def test_resposta_com_a_ultima_cota_pausa_antes_da_proxima_chamada(tmp_path, esperas):
    ultima = RespostaFalsa(200, {"data": {}}, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(AGORA + 50)})
    client = cliente_graphql(tmp_path, ultima)

    client.graphql(CONSULTA, VARIAVEIS)

    assert esperas == [52]


def test_erro_5xx_persistente_faz_backoff_exponencial_e_desiste(tmp_path, esperas):
    client = cliente_graphql(tmp_path, *[RespostaFalsa(502, {"message": "Bad Gateway"})] * 6)

    with pytest.raises(RuntimeError, match="HTTP 502"):
        client.graphql(CONSULTA, VARIAVEIS)

    assert esperas == [1, 2, 4, 8, 16]
    assert list(tmp_path.glob("*.json")) == []


def test_erro_5xx_temporario_e_queda_de_rede_sao_repetidos(tmp_path, esperas):
    client = cliente_graphql(
        tmp_path, RespostaFalsa(502, None, texto="<html>Bad Gateway</html>"),
        requests.ConnectionError("sem rede"), ok(),
    )

    status, _ = client.graphql(CONSULTA, VARIAVEIS)

    assert status == 200
    assert esperas == [1, 2]
