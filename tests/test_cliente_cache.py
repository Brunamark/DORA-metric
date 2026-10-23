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

from selecao_repos import ErroDeToken, ErroHttpPersistente  # noqa: E402


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
    """Cliente cuja sessão devolve as respostas na ordem; uma exceção na fila é lançada
    (simula Ctrl+C ou queda de rede)."""
    client = GitHubClient("token-de-teste", tmp_path)
    fila = list(respostas)

    def responder(*a, **kw):
        item = fila.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    client.session.get = responder
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


# --------------------------------------------------------------------------
# Retomada depois de Ctrl+C, rate limit e backoff exponencial
# --------------------------------------------------------------------------
import requests  # noqa: E402

AGORA = 1_000_000


@pytest.fixture
def esperas(monkeypatch):
    """Relógio parado em AGORA e time.sleep sem dormir: devolve a lista de esperas pedidas."""
    pedidas = []
    monkeypatch.setattr("selecao_repos.time.time", lambda: AGORA)
    monkeypatch.setattr("selecao_repos.time.sleep", pedidas.append)
    return pedidas


def sem_cota(status=403, reset=AGORA + 100):
    return RespostaFalsa(
        status,
        {"message": "API rate limit exceeded"},
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)},
    )


def test_ctrl_c_e_retomada_nao_repetem_chamadas_ja_feitas(tmp_path):
    primeira = cliente_com_respostas(tmp_path, RespostaFalsa(200, ["mes 1"]), KeyboardInterrupt())
    primeira.get("/repos/org/projeto/actions/runs", {"page": 1})
    with pytest.raises(KeyboardInterrupt):
        primeira.get("/repos/org/projeto/actions/runs", {"page": 2})

    retomada = cliente_com_respostas(tmp_path, RespostaFalsa(200, ["mes 2"]))
    pagina_1 = retomada.get("/repos/org/projeto/actions/runs", {"page": 1})
    pagina_2 = retomada.get("/repos/org/projeto/actions/runs", {"page": 2})

    assert (pagina_1[1], pagina_2[1]) == (["mes 1"], ["mes 2"])
    assert (retomada.chamadas, retomada.cache_hits) == (1, 1)


def test_cota_esgotada_pausa_ate_o_reset_e_repete(tmp_path, esperas):
    client = cliente_com_respostas(tmp_path, sem_cota(), RespostaFalsa(200, [1]))

    assert client.get("/repos/org/projeto/tags") == (200, [1], None)
    assert esperas == [102]          # até o X-RateLimit-Reset, com 2 s de folga
    assert client.chamadas == 2


def test_cota_esgotada_com_429_tambem_pausa(tmp_path, esperas):
    client = cliente_com_respostas(tmp_path, sem_cota(status=429, reset=AGORA + 10), RespostaFalsa(200, [1]))

    client.get("/repos/org/projeto/tags")

    assert esperas == [12]


def test_rate_limit_secundario_respeita_retry_after(tmp_path, esperas):
    limitado = RespostaFalsa(403, {"message": "secondary rate limit"}, headers={"Retry-After": "30"})
    client = cliente_com_respostas(tmp_path, limitado, RespostaFalsa(200, [1]))

    client.get("/repos/org/projeto/tags")

    assert esperas == [31]


def test_resposta_com_a_ultima_cota_pausa_antes_da_proxima_chamada(tmp_path, esperas):
    ultima = RespostaFalsa(200, [1], headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(AGORA + 50)})
    client = cliente_com_respostas(tmp_path, ultima)

    assert client.get("/repos/org/projeto/tags") == (200, [1], None)
    assert esperas == [52]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_resposta_de_rate_limit_nao_vai_para_o_cache(tmp_path, esperas):
    client = cliente_com_respostas(tmp_path, sem_cota(), RespostaFalsa(200, [1]))

    client.get("/repos/org/projeto/tags")

    salvo = json.loads(client._arquivo_cache(API + "/repos/org/projeto/tags", None).read_text(encoding="utf-8"))
    assert salvo["status"] == 200


def test_erro_5xx_persistente_faz_backoff_exponencial_e_desiste(tmp_path, esperas):
    client = cliente_com_respostas(tmp_path, *[RespostaFalsa(502, {"message": "Bad Gateway"})] * 6)

    with pytest.raises(ErroHttpPersistente, match="HTTP 502") as exc:
        client.get("/repos/org/projeto/tags")

    assert exc.value.status == 502
    assert esperas == [1, 2, 4, 8, 16]
    assert client.chamadas == 6
    assert list(tmp_path.glob("*.json")) == []


def test_erro_5xx_temporario_e_repetido_e_so_o_sucesso_vai_para_o_cache(tmp_path, esperas):
    client = cliente_com_respostas(
        tmp_path, RespostaFalsa(503, {"message": "Unavailable"}), RespostaFalsa(500, None, texto=""),
        RespostaFalsa(200, [1]),
    )

    assert client.get("/repos/org/projeto/tags") == (200, [1], None)
    assert esperas == [1, 2]
    salvo = json.loads(client._arquivo_cache(API + "/repos/org/projeto/tags", None).read_text(encoding="utf-8"))
    assert salvo["status"] == 200


def test_queda_de_rede_tambem_faz_backoff(tmp_path, esperas):
    client = cliente_com_respostas(tmp_path, requests.ConnectionError("sem rede"), RespostaFalsa(200, [1]))

    assert client.get("/repos/org/projeto/tags") == (200, [1], None)
    assert esperas == [1]


def test_erro_4xx_definitivo_nao_e_repetido_e_fica_no_cache(tmp_path, esperas):
    client = cliente_com_respostas(tmp_path, RespostaFalsa(404, {"message": "Not Found"}))

    client.get("/repos/org/projeto/compare/v1...v2")
    client.get("/repos/org/projeto/compare/v1...v2")

    assert esperas == []
    assert (client.chamadas, client.cache_hits) == (1, 1)
