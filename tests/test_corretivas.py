import csv
from datetime import timedelta

import pytest

from coleta_releases import VERSAO_CACHE_COMPARE
from conftest import REPO, caminho_compare, caminho_releases, commit, compare, link_proxima, release
from corretivas import executar, processar_repo
from selecao_repos import ErroDeToken


def resumo(resultado, pareamento="linha", criterio="semver_e_mensagem"):
    return next(r for r in resultado["resumo"] if r["pareamento"] == pareamento and r["criterio"] == criterio)


def linha_da(resultado, tag, pareamento="linha"):
    return next(r for r in resultado["releases"] if r["tag_name"] == tag and r["pareamento"] == pareamento)


@pytest.fixture
def exemplo_enunciado(cliente):
    """v2.3.0 (10/05) -> v2.3.1 (12/05, fix) -> v2.4.0 (01/06) -> v2.5.0 (20/06)."""
    return cliente({
        (caminho_releases(), 1): (200, [
            release("v2.5.0", "2026-06-20T00:00:00Z"),
            release("v2.4.0", "2026-06-01T00:00:00Z"),
            release("v2.3.1", "2026-05-12T00:00:00Z"),
            release("v2.3.0", "2026-05-10T00:00:00Z"),
        ], None),
        (caminho_compare("v2.3.0", "v2.3.1"), 1): compare(commit("a", "2026-05-11T00:00:00Z", "fix: crash ao abrir arquivo")),
        (caminho_compare("v2.3.1", "v2.4.0"), 1): compare(commit("b", "2026-05-20T00:00:00Z", "feat: nova tela")),
        (caminho_compare("v2.4.0", "v2.5.0"), 1): compare(commit("c", "2026-06-10T00:00:00Z", "feat: exportar")),
    })


def test_exemplo_do_enunciado_ponta_a_ponta(exemplo_enunciado, janela):
    resultado = processar_repo(exemplo_enunciado, REPO, *janela)

    r = resumo(resultado)
    assert (r["cfr_b"], r["releases_avaliadas"], r["releases_falharam"], r["releases_censuradas"]) == (0.25, 4, 1, 0)
    assert linha_da(resultado, "v2.3.0")["situacao_cfr"] == "falhou"
    assert linha_da(resultado, "v2.4.0")["situacao_cfr"] == "nao_falhou"
    v231 = linha_da(resultado, "v2.3.1")
    assert (v231["tipo_mudanca"], v231["n_fix"], v231["corretiva_semver_e_mensagem"]) == ("patch", 1, "sim")
    assert linha_da(resultado, "v2.3.0")["status_compare"] == "sem_predecessora"
    assert v231["patch_recente_7d"] == v231["corretiva_relatorio_patch_7d"] == "sim"   # 2 dias após v2.3.0
    assert linha_da(resultado, "v2.4.0")["corretiva_relatorio_patch_7d"] == "nao"


def test_cada_par_e_buscado_uma_vez_mesmo_com_dois_pareamentos(exemplo_enunciado, janela):
    processar_repo(exemplo_enunciado, REPO, *janela)

    compares = [c for c in exemplo_enunciado.chamadas if "/compare/" in c[0]]
    assert len(compares) == len(set(compares)) == 3


def test_pareamento_cronologico_usa_a_mesma_chave_de_cache_do_lead_time(exemplo_enunciado, janela):
    processar_repo(exemplo_enunciado, REPO, *janela)

    assert exemplo_enunciado.versoes_cache[(caminho_compare("v2.3.0", "v2.3.1"), 1)] == VERSAO_CACHE_COMPARE


def test_linhas_paralelas_mudam_o_resultado(cliente, janela):
    """25.8.10 corrige 25.8.9, mas foi publicada logo depois de 25.9.3 (outra linha)."""
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v25.8.10", "2026-05-03T00:00:00Z"),
            release("v25.9.3", "2026-05-02T00:00:00Z"),
            release("v25.8.9", "2026-05-01T00:00:00Z"),
        ], None),
        (caminho_compare("v25.8.9", "v25.9.3"), 1): compare(commit("a", "2026-04-30T00:00:00Z", "feat: x")),
        (caminho_compare("v25.8.9", "v25.8.10"), 1): compare(commit("b", "2026-05-02T00:00:00Z", "fix: backport")),
        (caminho_compare("v25.9.3", "v25.8.10"), 1): compare(commit("b", "2026-05-02T00:00:00Z", "fix: backport")),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert linha_da(resultado, "v25.8.10", "linha")["predecessora"] == "v25.8.9"
    assert linha_da(resultado, "v25.8.9", "linha")["situacao_cfr"] == "falhou"
    cron = linha_da(resultado, "v25.8.10", "cronologico")
    assert (cron["predecessora"], cron["tipo_mudanca"], cron["corretiva_semver_e_mensagem"]) == ("v25.9.3", "regressao", "nao")
    assert linha_da(resultado, "v25.8.9", "cronologico")["situacao_cfr"] == "nao_falhou"


def test_compare_novo_respeita_o_limite_de_paginas(cliente, janela):
    caminho = caminho_compare("v1.0.0", "v1.0.1")
    pagina = [commit(f"s{i}", "2026-05-01T00:00:00Z", "feat: x") for i in range(100)]
    api = cliente({
        (caminho_releases(), 1): (200, [release("v1.0.1", "2026-05-02T00:00:00Z"), release("v1.0.0", "2026-05-01T00:00:00Z")], None),
        (caminho, 1): (200, {"total_commits": 5000, "commits": pagina}, link_proxima(2)),
        (caminho, 2): (200, {"total_commits": 5000, "commits": pagina}, link_proxima(3)),
        (caminho, 3): (200, {"total_commits": 5000, "commits": pagina}, link_proxima(4)),
    })

    resultado = processar_repo(api, REPO, *janela, max_paginas=2)

    assert (caminho, 3) not in api.chamadas
    linha = linha_da(resultado, "v1.0.1")
    assert (linha["n_commits"], linha["total_commits_api"], linha["commits_truncados"]) == (200, 5000, "sim")
    assert resumo(resultado)["compares_truncados"] == 1


def test_compare_404_deixa_a_release_indeterminada(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v1.1.0", "2026-05-03T00:00:00Z"),
            release("v1.0.1", "2026-05-02T00:00:00Z"),
            release("v1.0.0", "2026-05-01T00:00:00Z"),
        ], None),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert linha_da(resultado, "v1.0.1")["corretiva_semver_e_mensagem"] == ""      # patch, commits desconhecidos
    assert linha_da(resultado, "v1.1.0")["corretiva_semver_e_mensagem"] == "nao"   # minor decide sozinho
    r = resumo(resultado)
    assert (r["compares_404"], r["releases_indeterminadas"]) == (2, 1)


def test_outro_erro_no_compare_e_contado_separado_do_404(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [release("v1.0.1", "2026-05-02T00:00:00Z"), release("v1.0.0", "2026-05-01T00:00:00Z")], None),
        (caminho_compare("v1.0.0", "v1.0.1"), 1): (500, None, None),
    })

    resultado = processar_repo(api, REPO, *janela)

    assert linha_da(resultado, "v1.0.1")["status_compare"] == "erro_http_500"
    assert (resumo(resultado)["compares_erro"], resumo(resultado)["compares_404"]) == (1, 0)


def test_release_nos_ultimos_7_dias_e_censurada(cliente, janela):
    _, fim = janela
    perto_do_fim = (fim - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    api = cliente({(caminho_releases(), 1): (200, [release("v1.0.0", perto_do_fim)], None)})

    r = resumo(processar_repo(api, REPO, *janela))

    assert (r["cfr_b"], r["releases_avaliadas"], r["releases_censuradas"]) == ("", 0, 1)


def test_notas_da_release_sao_aproveitadas_sem_chamada_nova(cliente, janela):
    com_notas = release("v1.0.0", "2026-05-01T00:00:00Z")
    com_notas["body"] = "## Bug Fixes\n- fixed crash on startup"
    api = cliente({(caminho_releases(), 1): (200, [com_notas], None)})

    resultado = processar_repo(api, REPO, *janela)

    assert linha_da(resultado, "v1.0.0")["notas_mencionam_correcao"] == "sim"


def test_listagem_vai_ate_um_ano_antes_da_janela(cliente, janela):
    pagina_1 = [release(f"v2.{i}.0", "2026-05-01T00:00:00Z") for i in range(100)]
    pagina_2 = [release("v1.9.0", "2025-03-15T00:00:00Z")]          # ~200 dias antes do início
    api = cliente({
        (caminho_releases(), 1): (200, pagina_1, link_proxima(2)),
        (caminho_releases(), 2): (200, pagina_2, link_proxima(3)),
        (caminho_releases(), 3): (200, [], None),
    })

    processar_repo(api, REPO, *janela)

    assert (caminho_releases(), 3) in api.chamadas


def test_erro_ao_listar_releases_fica_no_resumo(cliente, janela):
    api = cliente({(caminho_releases(), 1): (403, {"message": "Forbidden"}, None)})

    resultado = processar_repo(api, REPO, *janela)

    assert resultado["resumo"][0]["status"] == "erro_http_403"
    assert resultado["releases"] == []


# --------------------------------------------------------------------------
# Etapa completa: CSVs e isolamento de erros
# --------------------------------------------------------------------------
class ClienteComContadores:
    def __init__(self, interno, falhar_em=None, erro=ValueError):
        self.interno, self.falhar_em, self.erro = interno, falhar_em, erro
        self.chamadas, self.cache_hits = 0, 0

    def get(self, path, *a, **kw):
        if self.falhar_em and self.falhar_em in path:
            raise self.erro("falha simulada")
        self.chamadas += 1
        return self.interno.get(path, *a, **kw)


def test_executar_grava_os_csvs(exemplo_enunciado, janela, tmp_path):
    executar(ClienteComContadores(exemplo_enunciado), *janela, [{"full_name": REPO}], tmp_path)

    with (tmp_path / "cfr_entrega_repos.csv").open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == 2 * 7           # pareamentos x critérios (a regra do relatório ignora o pareamento)
    with (tmp_path / "releases_corretivas.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 2 * 4


def test_erro_inesperado_num_repositorio_nao_derruba_a_etapa(exemplo_enunciado, janela, tmp_path):
    api = ClienteComContadores(exemplo_enunciado, falhar_em="/repos/org/quebrado/")
    repos = [{"full_name": "org/quebrado"}, {"full_name": REPO}]

    resumos = executar(api, *janela, repos, tmp_path)

    assert resumos[0]["status"].startswith("erro: falha simulada")
    assert any(r["full_name"] == REPO and r["status"] == "ok" for r in resumos)


def test_token_invalido_interrompe_a_etapa(exemplo_enunciado, janela, tmp_path):
    api = ClienteComContadores(exemplo_enunciado, falhar_em="/repos/", erro=ErroDeToken)

    with pytest.raises(ErroDeToken):
        executar(api, *janela, [{"full_name": REPO}], tmp_path)
