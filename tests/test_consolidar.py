"""consolidar.py: dataset com uma linha por repositório, a partir de CSVs pequenos com
resultado conhecido (sem API)."""

import csv

import pytest

import consolidar
from conftest import REPO
from metricas import CRITERIO_PADRAO, PAREAMENTO_PADRAO
from selecao_repos import parse_janela

OUTRO = "org/outro"
INI, FIM = parse_janela("2025-10-01", "2026-10-01")
SEMANAS = (FIM - INI).total_seconds() / (7 * 86400)


def gravar(caminho, linhas):
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)


def repo(fn):
    return {
        "full_name": fn, "url": f"https://github.com/{fn}", "stars": 1500, "language": "Python",
        "contributors": 12, "created_at": "2020-01-01T00:00:00Z", "age_days": 2100,
        "default_branch": "main", "releases_in_window": 52, "valid_runs_in_window": 300,
    }


def lead_time(fn, n_releases=52, status="ok"):
    return {
        "full_name": fn, "status_releases": status, "status_tags": "ok", "releases_na_janela": n_releases,
        "releases_calculadas": n_releases, "releases_sem_commits": 0, "releases_404": 1, "releases_erro": 0,
        "releases_commits_incompletos": 0, "commits": 100, "commits_lead_time_negativo": 0,
        "lead_time_release_mediana_dias": 13.0, "lead_time_commit_mediana_dias": 5.0,
    }


def variantes(fn, n_releases=104):
    return {
        "full_name": fn, "status_releases_c2": "ok", "releases_na_janela_c2": n_releases,
        "releases_calculadas_c2": n_releases, "releases_sem_commits_c2": 0, "releases_404_c2": 2,
        "releases_erro_c2": 0, "releases_commits_incompletos_c2": 0, "commits_c2": 120,
        "commits_lead_time_negativo_c2": 0, "lead_time_release_mediana_dias_c2": 7.5,
        "lead_time_commit_mediana_dias_c2": 2.5, "status_tags_datas": "ok", "tags": 4, "tags_sem_data": 1,
    }


def runs(fn):
    return {
        "full_name": fn, "default_branch": "main", "status_runs": "ok", "fatias_consultadas": 13,
        "fatias_divididas": 0, "fatias_no_teto": 0, "runs_coletados": 300, "runs_sucesso": 240,
        "runs_falha": 60, "runs_ignorados": 0, "workflows": 2, "cfr_a": 0.2, "episodios": 10,
        "episodios_fechados": 9, "episodios_censurados": 1, "proporcao_censurados": 0.1,
        "workflows_falha_sem_sucesso_anterior": 0, "tempo_recuperacao_mediana_horas": 1.3333,
    }


def tags(fn):
    """4 tags: duas na janela, uma antes dela e uma sem data."""
    base = {"full_name": fn, "sha": "a" * 40}
    return [
        {**base, "tag_name": "v3", "commit_date": "2026-05-01T12:00:00Z"},
        {**base, "tag_name": "v2", "commit_date": "2025-10-01T00:00:00Z"},
        {**base, "tag_name": "v1", "commit_date": "2025-09-30T23:59:59Z"},
        {**base, "tag_name": "v0", "commit_date": ""},
    ]


def cfr_b(fn):
    comum = {"full_name": fn, "status": "ok", "releases_avaliadas": 50, "releases_censuradas": 2}
    return [
        {**comum, "pareamento": PAREAMENTO_PADRAO, "criterio": CRITERIO_PADRAO, "cfr_b": 0.1},
        {**comum, "pareamento": "cronologico", "criterio": CRITERIO_PADRAO, "cfr_b": 0.9},
        {**comum, "pareamento": PAREAMENTO_PADRAO, "criterio": "so_semver", "cfr_b": 0.8},
    ]


@pytest.fixture
def pasta(tmp_path):
    """CSVs de todas as etapas para um repositório com valores conhecidos."""
    gravar(tmp_path / "repos_selecionados.csv", [repo(REPO)])
    gravar(tmp_path / "lead_time_repos.csv", [lead_time(REPO)])
    gravar(tmp_path / "variantes_repos.csv", [variantes(REPO)])
    gravar(tmp_path / "workflow_runs_repos.csv", [runs(REPO)])
    gravar(tmp_path / "tags.csv", tags(REPO))
    return tmp_path


def ler_dataset(pasta):
    with (pasta / "dataset.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_juncao_completa_com_valores_conhecidos(pasta):
    consolidar.executar(INI, FIM, pasta)

    [linha] = ler_dataset(pasta)
    assert linha["full_name"] == REPO
    assert linha["stars"] == "1500"
    assert linha["lead_time_a_dias"] == "13.0"
    assert linha["lead_time_b_dias"] == "5.0"
    assert linha["lead_time_a_dias_c2"] == "7.5"
    assert linha["lead_time_b_dias_c2"] == "2.5"
    assert linha["cfr_a"] == "0.2"
    assert linha["tempo_recuperacao_horas"] == "1.3333"
    assert linha["proporcao_censurados"] == "0.1"
    assert linha["releases_404"] == "1"
    assert linha["releases_404_c2"] == "2"
    assert linha["fatias_no_teto"] == "0"
    assert list(linha) == consolidar.COLUNAS_DATASET


def test_frequencia_de_deploy_nas_tres_unidades(pasta):
    dataset = consolidar.consolidar(pasta, INI, FIM)

    linha = dataset.iloc[0]
    assert linha["freq_deploy_release"] == pytest.approx(round(52 / SEMANAS, 4))
    assert linha["freq_deploy_release_pre"] == pytest.approx(round(104 / SEMANAS, 4))
    # só as duas tags com commit_date na janela contam (a de antes e a sem data, não)
    assert linha["tags_na_janela"] == 2
    assert linha["freq_deploy_tag"] == pytest.approx(round(2 / SEMANAS, 4))


def test_janela_de_365_dias_tem_cerca_de_52_semanas(pasta):
    dataset = consolidar.consolidar(pasta, INI, FIM)

    assert dataset.iloc[0]["freq_deploy_release"] == pytest.approx(1.0, abs=0.01)


def test_repositorio_ausente_numa_fonte_continua_com_metricas_vazias(pasta, capsys):
    gravar(pasta / "repos_selecionados.csv", [repo(REPO), repo(OUTRO)])

    consolidar.executar(INI, FIM, pasta)

    linhas = {l["full_name"]: l for l in ler_dataset(pasta)}
    assert set(linhas) == {REPO, OUTRO}
    outro = linhas[OUTRO]
    assert outro["stars"] == "1500"
    for coluna in ("lead_time_a_dias", "cfr_a", "freq_deploy_release", "freq_deploy_release_pre",
                   "freq_deploy_tag", "tags_na_janela", "status_runs"):
        assert outro[coluna] == "", coluna
    assert "sem linha em lead_time_repos.csv" in capsys.readouterr().out


def test_erro_ao_listar_releases_deixa_a_frequencia_vazia(pasta):
    gravar(pasta / "lead_time_repos.csv", [lead_time(REPO, n_releases=0, status="erro_http_404")])

    dataset = consolidar.consolidar(pasta, INI, FIM)

    assert dataset.iloc[0]["freq_deploy_release"] is None


def test_repositorio_sem_tags_tem_frequencia_zero_na_unidade_tag(pasta):
    gravar(pasta / "tags.csv", tags(OUTRO))

    dataset = consolidar.consolidar(pasta, INI, FIM)

    assert dataset.iloc[0]["tags_na_janela"] == 0
    assert dataset.iloc[0]["freq_deploy_tag"] == 0


def test_cfr_b_fica_fora_por_padrao(pasta):
    gravar(pasta / "cfr_entrega_repos.csv", cfr_b(REPO))

    consolidar.executar(INI, FIM, pasta)

    assert "cfr_b" not in ler_dataset(pasta)[0]


def test_cfr_b_com_a_opcao_usa_pareamento_e_criterio_padrao(pasta):
    gravar(pasta / "cfr_entrega_repos.csv", cfr_b(REPO))

    consolidar.executar(INI, FIM, pasta, incluir_cfr_b=True)

    [linha] = ler_dataset(pasta)
    assert linha["cfr_b"] == "0.1"
    assert linha["releases_avaliadas_cfr_b"] == "50"
    assert linha["releases_censuradas_cfr_b"] == "2"
    assert linha["status_cfr_b"] == "ok"


def test_cfr_b_pedido_sem_a_etapa_corretivas_para_com_mensagem(pasta):
    with pytest.raises(SystemExit, match="corretivas"):
        consolidar.executar(INI, FIM, pasta, incluir_cfr_b=True)


def test_fonte_obrigatoria_ausente_para_com_mensagem(pasta):
    (pasta / "workflow_runs_repos.csv").unlink()

    with pytest.raises(SystemExit, match="etapa runs"):
        consolidar.executar(INI, FIM, pasta)


def test_tags_sem_commit_date_pede_a_etapa_variantes(pasta):
    gravar(pasta / "tags.csv", [{"full_name": REPO, "tag_name": "v1", "sha": "a" * 40}])

    with pytest.raises(SystemExit, match="variantes"):
        consolidar.executar(INI, FIM, pasta)


def test_rodar_duas_vezes_gera_o_mesmo_arquivo(pasta):
    consolidar.executar(INI, FIM, pasta)
    primeiro = (pasta / "dataset.csv").read_bytes()
    consolidar.executar(INI, FIM, pasta)

    assert (pasta / "dataset.csv").read_bytes() == primeiro
