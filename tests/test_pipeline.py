"""pipeline.py: etapas na ordem do pipeline, com o mesmo cliente e a mesma janela."""

import pytest

import pipeline
from conftest import REPO


class ClienteSemApi:
    chamadas = 0
    cache_hits = 0

    def __init__(self, token, cache_dir):
        pass


@pytest.fixture
def executadas(monkeypatch, tmp_path):
    """Troca o executar() de cada etapa por um registrador e devolve a lista de etapas
    executadas, cada uma com os repositórios recebidos (None na seleção)."""
    ordem = []
    monkeypatch.setattr(pipeline, "ler_token", lambda: "token-de-teste")
    monkeypatch.setattr(pipeline, "GitHubClient", ClienteSemApi)
    monkeypatch.setattr(pipeline.selecao_repos, "executar", lambda *a, **kw: ordem.append(("selecao", None)))
    for nome, modulo in [
        ("releases", pipeline.coleta_releases),
        ("variantes", pipeline.variantes),
        ("runs", pipeline.coleta_runs),
        ("corretivas", pipeline.corretivas),
    ]:
        monkeypatch.setattr(modulo, "executar", lambda c, i, f, repos, s, *a, _n=nome: ordem.append((_n, repos)))
    monkeypatch.setattr(pipeline.consolidar, "executar",
                        lambda i, f, s, incluir_cfr_b: ordem.append(("consolidar", incluir_cfr_b)))
    (tmp_path / "repos_selecionados.csv").write_text(f"full_name,default_branch\n{REPO},main\n", encoding="utf-8")
    return ordem


def rodar(tmp_path, *extra):
    pipeline.main([
        "--inicio", "2025-10-01", "--fim", "2026-10-01",
        "--saida", str(tmp_path), "--cache", str(tmp_path / "cache"), *extra,
    ])


def test_padrao_roda_variantes_logo_depois_de_releases(executadas, tmp_path):
    rodar(tmp_path)

    assert [nome for nome, _ in executadas] == ["selecao", "releases", "variantes", "runs", "consolidar"]


def test_etapas_pedidas_fora_de_ordem_rodam_na_ordem_do_pipeline(executadas, tmp_path):
    rodar(tmp_path, "--etapas", "runs", "variantes", "releases")

    assert [nome for nome, _ in executadas] == ["releases", "variantes", "runs"]


def test_variantes_recebe_os_repositorios_da_selecao(executadas, tmp_path):
    rodar(tmp_path, "--etapas", "variantes")

    assert executadas == [("variantes", [{"full_name": REPO, "default_branch": "main"}])]


def test_corretivas_continua_fora_do_padrao(executadas, tmp_path):
    rodar(tmp_path)

    assert "corretivas" not in [nome for nome, _ in executadas]


def test_consolidar_e_a_ultima_etapa(executadas, tmp_path):
    rodar(tmp_path, "--etapas", "consolidar", "corretivas", "runs")

    assert [nome for nome, _ in executadas] == ["runs", "corretivas", "consolidar"]


def test_consolidar_sozinha_roda_sem_token_e_sem_cliente(monkeypatch, tmp_path):
    def sem_token():
        raise AssertionError("consolidar não deveria pedir o token")

    def sem_cliente(*a, **kw):
        raise AssertionError("consolidar não deveria criar o cliente da API")

    chamadas = []
    monkeypatch.setattr(pipeline, "ler_token", sem_token)
    monkeypatch.setattr(pipeline, "GitHubClient", sem_cliente)
    monkeypatch.setattr(pipeline.consolidar, "executar", lambda i, f, s, incluir_cfr_b: chamadas.append(s))

    rodar(tmp_path, "--etapas", "consolidar")

    assert chamadas == [tmp_path]


def test_incluir_cfr_b_e_repassado_ao_consolidar(executadas, tmp_path):
    rodar(tmp_path, "--etapas", "consolidar", "--incluir-cfr-b")

    assert executadas == [("consolidar", True)]


def test_cfr_b_fica_fora_do_consolidar_por_padrao(executadas, tmp_path):
    rodar(tmp_path, "--etapas", "consolidar")

    assert executadas == [("consolidar", False)]
