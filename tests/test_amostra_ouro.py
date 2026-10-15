"""Sorteio da amostra-ouro: reprodutibilidade, elegibilidade das releases e planilhas."""

import json

import pandas as pd
import pytest

from amostra_ouro import (
    N_RELEASES,
    N_REPOS,
    SEED,
    gravar,
    links,
    main,
    montar_planilha,
    releases_avaliaveis,
    sortear_amostra_ouro,
)
from dados_validacao import INTEGRANTES, fazer_releases, fazer_repos
from validar_rotulos import COLUNAS_PLANILHA, DIMENSOES, ler_csv


@pytest.fixture
def repos():
    return fazer_repos(80)


@pytest.fixture
def releases(repos):
    return fazer_releases(repos)


# --------------------------------------------------------------------------
# Tamanho e reprodutibilidade
# --------------------------------------------------------------------------
def test_sorteia_60_repositorios_com_5_releases_cada(repos, releases):
    amostra, _ = sortear_amostra_ouro(repos, releases)

    assert amostra["repo"].nunique() == N_REPOS == 60
    assert len(amostra) == 60 * N_RELEASES == 300
    assert (amostra.groupby("repo").size() == 5).all()
    assert not amostra.duplicated(["repo", "tag"]).any()


def test_rodar_duas_vezes_gera_exatamente_as_mesmas_60_x_5_releases(repos, releases):
    primeira, resumo1 = sortear_amostra_ouro(repos, releases)
    segunda, resumo2 = sortear_amostra_ouro(repos.copy(), releases.copy())

    pd.testing.assert_frame_equal(primeira, segunda)
    assert resumo1 == resumo2


def test_a_ordem_das_linhas_dos_csvs_de_entrada_nao_muda_o_sorteio(repos, releases):
    esperada, _ = sortear_amostra_ouro(repos, releases)

    embaralhada, _ = sortear_amostra_ouro(
        repos.sample(frac=1, random_state=7), releases.sample(frac=1, random_state=11)
    )

    pd.testing.assert_frame_equal(esperada, embaralhada)


def test_a_semente_e_42_e_mudar_a_semente_muda_o_sorteio(repos, releases):
    assert SEED == 42
    padrao, _ = sortear_amostra_ouro(repos, releases)

    outra, _ = sortear_amostra_ouro(repos, releases, seed=43)

    assert not padrao.equals(outra)


def test_repositorios_sorteados_seguem_df_sample_n_60_random_state_42(repos, releases):
    amostra, _ = sortear_amostra_ouro(repos, releases)

    esperados = pd.Series(sorted(repos["full_name"])).sample(n=60, random_state=42).sort_values()
    assert list(amostra["repo"].unique()) == list(esperados)


# --------------------------------------------------------------------------
# Releases avaliáveis
# --------------------------------------------------------------------------
def test_so_entram_releases_da_janela_com_anterior_e_compare_resolvido(repos, releases):
    amostra, _ = sortear_amostra_ouro(repos, releases)

    sorteadas = amostra.merge(
        releases, left_on=["repo", "tag"], right_on=["full_name", "tag_name"],
        suffixes=("", "_csv"), validate="one_to_one",
    )
    assert (sorteadas["na_janela"] == "True").all()
    assert (sorteadas["tag_anterior"] != "").all()
    assert (sorteadas["tag_anterior"] == sorteadas["tag_anterior_csv"]).all()
    assert sorteadas["status"].isin(["ok", "sem_commits"]).all()


def test_primeira_release_do_historico_nao_e_avaliavel():
    repos = fazer_repos(1)
    releases = fazer_releases(repos, por_repo=3)
    releases.loc[releases["tag_name"] == "v1.0", ["tag_anterior", "status"]] = ["", "primeira_release"]

    avaliaveis = releases_avaliaveis(releases)

    assert set(avaliaveis["tag_name"]) == {"v1.1", "v1.2"}


@pytest.mark.parametrize("status", ["tag_404", "erro_http_500", "primeira_release", "fora_da_janela",
                                    "excluida_draft", "excluida_prerelease"])
def test_releases_sem_compare_utilizavel_ficam_de_fora(status):
    releases = fazer_releases(fazer_repos(1), por_repo=2)
    releases.loc[releases["tag_name"] == "v1.1", "status"] = status

    assert "v1.1" not in set(releases_avaliaveis(releases)["tag_name"])


def test_release_fora_da_janela_fica_de_fora_mesmo_com_status_ok():
    releases = fazer_releases(fazer_repos(1), por_repo=2)
    releases.loc[releases["tag_name"] == "v1.1", "na_janela"] = "False"

    assert "v1.1" not in set(releases_avaliaveis(releases)["tag_name"])


def test_repositorio_com_menos_de_5_avaliaveis_nao_e_sorteado(repos):
    releases = fazer_releases(repos, r3=2)  # o repositório 3 fica com 2 releases avaliáveis

    amostra, resumo = sortear_amostra_ouro(repos, releases, n_repos=79)

    assert "org003/proj003" not in set(amostra["repo"])
    assert resumo["repos_elegiveis"] == 79


def test_sem_repositorios_suficientes_e_erro_claro(repos):
    releases = fazer_releases(repos, por_repo=4)  # 4 avaliáveis por repositório (< 5)

    with pytest.raises(ValueError, match="repositórios têm 5 ou mais releases avaliáveis"):
        sortear_amostra_ouro(repos, releases)


def test_repositorios_fora_da_amostra_final_sao_ignorados(releases):
    so_alguns = fazer_repos(70)  # releases.csv tem 80 repositórios; a amostra final, 70

    amostra, resumo = sortear_amostra_ouro(so_alguns, releases)

    assert set(amostra["repo"]) <= set(so_alguns["full_name"])
    assert resumo["repos_na_amostra_final"] == 70


def test_resumo_traz_os_numeros_para_a_metodologia(repos, releases):
    _, resumo = sortear_amostra_ouro(repos, releases)

    assert resumo["seed"] == 42
    assert resumo["repos_na_amostra_final"] == 80
    assert resumo["repos_elegiveis"] == 80
    assert resumo["releases_avaliaveis_total"] == 80 * 8


# --------------------------------------------------------------------------
# Planilhas
# --------------------------------------------------------------------------
def test_links_diretos_para_repositorio_release_e_commits():
    assert links("org/proj", "v1.1", "v1.0") == (
        "https://github.com/org/proj",
        "https://github.com/org/proj/releases/tag/v1.1",
        "https://github.com/org/proj/compare/v1.0...v1.1",
    )


def test_links_mantem_tags_com_barra_e_arroba_e_codifica_o_resto():
    _, release, commits = links("org/proj", "@scope/pkg@1.0.0", "release 1#0")

    assert release == "https://github.com/org/proj/releases/tag/@scope/pkg@1.0.0"
    assert commits == "https://github.com/org/proj/compare/release%201%230...@scope/pkg@1.0.0"


def test_planilha_tem_links_e_colunas_dos_rotulos_vazias(repos, releases):
    amostra, _ = sortear_amostra_ouro(repos, releases)

    planilha = montar_planilha(amostra)

    assert list(planilha.columns) == list(COLUNAS_PLANILHA)
    assert len(planilha) == 300
    assert planilha["link_repo"].str.fullmatch(r"https://github\.com/[^/]+/[^/]+").all()
    assert planilha["link_release"].str.contains("/releases/tag/").all()
    assert planilha["link_commits"].str.contains(r"/compare/.+\.\.\..+").all()
    for dimensao in DIMENSOES:
        assert (planilha[dimensao] == "").all()


def test_planilha_nao_traz_nenhuma_coluna_da_heuristica(repos, releases):
    amostra, _ = sortear_amostra_ouro(repos, releases)

    colunas = set(montar_planilha(amostra).columns)

    assert colunas == {"repo", "tag", "tag_anterior", "link_repo", "link_release", "link_commits",
                       "tipo_projeto", "releases_reais", "corretiva"}
    proibidas = ("heuristica", "predicao", "prevista", "patch", "semver", "score", "revert", "hotfix", "fix")
    assert not [c for c in colunas if any(p in c.lower() for p in proibidas)]


def test_gravar_cria_tres_planilhas_identicas(tmp_path, repos, releases):
    amostra, resumo = sortear_amostra_ouro(repos, releases)

    gravar(tmp_path, INTEGRANTES, amostra, resumo, forcar=False)

    conteudos = {(tmp_path / f"rotulos_{nome}.csv").read_bytes() for nome in INTEGRANTES}
    assert len(conteudos) == 1
    assert len(ler_csv(tmp_path / "rotulos_ana.csv")) == 300
    assert json.loads((tmp_path / "sorteio.json").read_text(encoding="utf-8"))["seed"] == 42
    assert list(ler_csv(tmp_path / "amostra_ouro.csv").columns) == ["repo", "tag", "tag_anterior"]


def test_gravar_nao_sobrescreve_planilhas_que_podem_ter_rotulos(tmp_path, repos, releases):
    amostra, resumo = sortear_amostra_ouro(repos, releases)
    gravar(tmp_path, INTEGRANTES, amostra, resumo, forcar=False)
    (tmp_path / "rotulos_ana.csv").write_text("rotulos preenchidos", encoding="utf-8")

    with pytest.raises(FileExistsError, match="rotulos_ana.csv"):
        gravar(tmp_path, INTEGRANTES, amostra, resumo, forcar=False)
    assert (tmp_path / "rotulos_ana.csv").read_text(encoding="utf-8") == "rotulos preenchidos"

    gravar(tmp_path, INTEGRANTES, amostra, resumo, forcar=True)
    assert len(ler_csv(tmp_path / "rotulos_ana.csv")) == 300


# --------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------
def _cli(monkeypatch, tmp_path, repos, releases, *extras, integrantes=INTEGRANTES):
    repos.to_csv(tmp_path / "repos.csv", index=False)
    releases.to_csv(tmp_path / "releases.csv", index=False)
    argv = ["amostra_ouro.py", "--integrantes", *integrantes,
            "--repos", str(tmp_path / "repos.csv"), "--releases", str(tmp_path / "releases.csv"),
            "--saida", str(tmp_path / "validacao"), *extras]
    monkeypatch.setattr("sys.argv", argv)
    main()


def test_cli_gera_amostra_e_planilhas(monkeypatch, tmp_path, repos, releases, capsys):
    _cli(monkeypatch, tmp_path, repos, releases)

    assert "60 repositórios x 5 releases = 300 linhas" in capsys.readouterr().out
    for nome in INTEGRANTES:
        assert (tmp_path / "validacao" / f"rotulos_{nome}.csv").exists()


def test_cli_segunda_execucao_recusa_sobrescrever(monkeypatch, tmp_path, repos, releases):
    _cli(monkeypatch, tmp_path, repos, releases)

    with pytest.raises(SystemExit, match="--forcar"):
        _cli(monkeypatch, tmp_path, repos, releases)


def test_cli_rejeita_nomes_que_nao_servem_de_nome_de_arquivo(monkeypatch, tmp_path, repos, releases):
    with pytest.raises(SystemExit, match="nomes únicos"):
        _cli(monkeypatch, tmp_path, repos, releases, integrantes=["ana", "../bruno", "carla"])
    with pytest.raises(SystemExit, match="nomes únicos"):
        _cli(monkeypatch, tmp_path, repos, releases, integrantes=["ana", "ana", "carla"])


def test_cli_sem_releases_csv_orienta_a_rodar_a_coleta(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["amostra_ouro.py", "--integrantes", "a", "b", "c",
                                     "--repos", str(tmp_path / "x.csv"), "--releases", str(tmp_path / "y.csv")])

    with pytest.raises(SystemExit, match="Rode a coleta"):
        main()
