"""Consenso: maioria simples automática e casos 1-1-1 encaminhados para a reunião."""

import pandas as pd
import pytest

from consenso import (
    ARQUIVO_CONSENSO,
    ARQUIVO_DECISOES,
    CAMPOS_CONSENSO,
    CAMPOS_DECISOES,
    construir_consenso,
    formatar_votos,
    ler_decisoes,
    main,
    maioria_simples,
    pendentes,
)
from dados_validacao import INTEGRANTES, preencher, rotulo_padrao, sortear_e_gravar
from validar_rotulos import carregar_rotulos, ler_csv


# --------------------------------------------------------------------------
# maioria_simples
# --------------------------------------------------------------------------
@pytest.mark.parametrize(("votos", "esperado"), [
    (["sim", "sim", "não"], "sim"),    # 2-1
    (["não", "sim", "sim"], "sim"),
    (["incerto", "sim", "incerto"], "incerto"),
    (["sim", "sim", "sim"], "sim"),    # 3-0
    (["sim", "não", "incerto"], None),  # 1-1-1
    (["a", "b", "c"], None),
])
def test_maioria_simples(votos, esperado):
    assert maioria_simples(votos) == esperado


def test_empate_sem_maioria_estrita_vai_para_reuniao():
    assert maioria_simples(["sim", "sim", "não", "não"]) is None


def test_formatar_votos_ordena_pelo_nome_do_avaliador():
    assert formatar_votos({"carla": "não", "ana": "sim", "bruno": "sim"}) == "ana=sim | bruno=sim | carla=não"


# --------------------------------------------------------------------------
# construir_consenso
# --------------------------------------------------------------------------
@pytest.fixture
def pasta(tmp_path):
    sortear_e_gravar(tmp_path)
    for nome in INTEGRANTES:
        preencher(tmp_path, nome, rotulo_padrao)
    return tmp_path


def alterar(pasta, nome, regras):
    """Reescreve a planilha de `nome`, trocando o rótulo de itens específicos.
    `regras`: {(dimensao, repo, tag): novo_valor}; tag vazia para dimensões do repositório."""
    def rotulo(dimensao, repo, tag):
        return regras.get((dimensao, repo, tag if dimensao == "corretiva" else ""), rotulo_padrao(dimensao, repo, tag))

    preencher(pasta, nome, rotulo)


def um_item(pasta):
    """(repo, tag) do primeiro item da amostra."""
    amostra = ler_csv(pasta / "amostra_ouro.csv")
    return amostra.loc[0, "repo"], amostra.loc[0, "tag"]


def linha(consenso, dimensao, repo, tag=""):
    achada = consenso[(consenso["dimensao"] == dimensao) & (consenso["repo"] == repo) & (consenso["tag"] == tag)]
    assert len(achada) == 1
    return achada.iloc[0]


def test_concordancia_total_resolve_tudo_por_maioria(pasta):
    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES))

    assert list(consenso.columns) == CAMPOS_CONSENSO
    assert len(consenso) == 8 + 8 + 40
    assert (consenso["decidido_em"] == "maioria").all()
    assert (consenso["rotulo_consenso"] != "").all()
    assert reuniao.empty and list(reuniao.columns) == CAMPOS_DECISOES


def test_maioria_2_a_1_e_resolvida_automaticamente(pasta):
    repo, tag = um_item(pasta)
    original = rotulo_padrao("corretiva", repo, tag)
    oposto = "não" if original == "sim" else "sim"
    alterar(pasta, "carla", {("corretiva", repo, tag): oposto})  # Carla discorda, Ana e Bruno concordam

    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES))

    item = linha(consenso, "corretiva", repo, tag)
    assert item["rotulo_consenso"] == original
    assert item["decidido_em"] == "maioria"
    assert item["votos"] == f"ana={original} | bruno={original} | carla={oposto}"
    assert reuniao.empty


def test_caso_1_1_1_vai_para_a_reuniao_sem_rotulo(pasta):
    repo, _ = um_item(pasta)
    alterar(pasta, "ana", {("releases_reais", repo, ""): "sim"})
    alterar(pasta, "bruno", {("releases_reais", repo, ""): "não"})
    alterar(pasta, "carla", {("releases_reais", repo, ""): "incerto"})

    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES))

    item = linha(consenso, "releases_reais", repo)
    assert item["decidido_em"] == "reuniao"
    assert item["rotulo_consenso"] == ""
    assert list(pendentes(consenso)["repo"]) == [repo]
    assert len(reuniao) == 1
    assert reuniao.iloc[0]["votos"] == "ana=sim | bruno=não | carla=incerto"
    assert reuniao.iloc[0]["rotulo_reuniao"] == ""


def test_so_o_caso_1_1_1_vai_para_a_reuniao_e_o_resto_segue_automatico(pasta):
    repo, _ = um_item(pasta)
    alterar(pasta, "ana", {("tipo_projeto", repo, ""): "outro"})
    alterar(pasta, "bruno", {("tipo_projeto", repo, ""): "ferramenta CLI"})
    alterar(pasta, "carla", {("tipo_projeto", repo, ""): "aplicação/serviço"})

    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES))

    assert len(reuniao) == 1
    assert (consenso["decidido_em"] == "reuniao").sum() == 1
    assert (consenso["decidido_em"] == "maioria").sum() == len(consenso) - 1


def test_decisao_da_reuniao_completa_o_consenso(pasta):
    repo, _ = um_item(pasta)
    for nome, valor in zip(INTEGRANTES, ["sim", "não", "incerto"]):
        alterar(pasta, nome, {("releases_reais", repo, ""): valor})
    decisoes = {("releases_reais", repo, ""): {"rotulo": "não", "observacao": "só publicam snapshots"}}

    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES), decisoes)

    item = linha(consenso, "releases_reais", repo)
    assert (item["rotulo_consenso"], item["decidido_em"]) == ("não", "reuniao")
    assert pendentes(consenso).empty
    assert reuniao.iloc[0]["rotulo_reuniao"] == "não"
    assert reuniao.iloc[0]["observacao"] == "só publicam snapshots"


def test_corretiva_com_dois_valores_nunca_cai_em_1_1_1(pasta):
    """Com 3 avaliadores e 2 categorias sempre há maioria."""
    repo, tag = um_item(pasta)
    for nome, valor in zip(INTEGRANTES, ["sim", "não", "sim"]):
        alterar(pasta, nome, {("corretiva", repo, tag): valor})

    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES))

    assert reuniao.empty
    assert linha(consenso, "corretiva", repo, tag)["rotulo_consenso"] == "sim"


# --------------------------------------------------------------------------
# decisoes_reuniao.csv
# --------------------------------------------------------------------------
def escrever_decisoes(pasta, linhas):
    pd.DataFrame(linhas, columns=CAMPOS_DECISOES).to_csv(pasta / ARQUIVO_DECISOES, index=False)


def test_ler_decisoes_sem_arquivo_e_vazio(tmp_path):
    assert ler_decisoes(tmp_path / ARQUIVO_DECISOES) == {}


def test_ler_decisoes_ignora_pendentes_e_normaliza_o_rotulo(tmp_path):
    escrever_decisoes(tmp_path, [
        ["releases_reais", "org/a", "", "x", " NAO ", "discutido"],
        ["tipo_projeto", "org/b", "", "x", "", ""],
    ])

    decisoes = ler_decisoes(tmp_path / ARQUIVO_DECISOES)

    assert decisoes == {("releases_reais", "org/a", ""): {"rotulo": "não", "observacao": "discutido"}}


def test_ler_decisoes_com_rotulo_invalido_aponta_a_linha(tmp_path):
    escrever_decisoes(tmp_path, [["releases_reais", "org/a", "", "x", "talvez", ""]])

    with pytest.raises(ValueError, match="linha 2.*'talvez' inválido para 'releases_reais'"):
        ler_decisoes(tmp_path / ARQUIVO_DECISOES)


def test_ler_decisoes_rejeita_colunas_ausentes(tmp_path):
    pd.DataFrame([["releases_reais", "org/a"]], columns=["dimensao", "repo"]).to_csv(
        tmp_path / ARQUIVO_DECISOES, index=False
    )

    with pytest.raises(ValueError, match="colunas ausentes.*tag.*votos"):
        ler_decisoes(tmp_path / ARQUIVO_DECISOES)


def test_rotulo_valido_para_outra_dimensao_e_rejeitado(tmp_path):
    escrever_decisoes(tmp_path, [["corretiva", "org/a", "v1", "x", "incerto", ""]])

    with pytest.raises(ValueError, match="inválido para 'corretiva'"):
        ler_decisoes(tmp_path / ARQUIVO_DECISOES)


def test_dimensao_desconhecida_na_decisao_e_erro(tmp_path):
    escrever_decisoes(tmp_path, [["velocidade", "org/a", "", "x", "sim", ""]])

    with pytest.raises(ValueError, match="inválido para 'velocidade'"):
        ler_decisoes(tmp_path / ARQUIVO_DECISOES)


def test_decisao_de_reuniao_so_afeta_item_sem_maioria(pasta):
    repo_empate, _ = um_item(pasta)
    repos = ler_csv(pasta / "amostra_ouro.csv")["repo"].drop_duplicates().tolist()
    repo_maioria = repos[1]
    for nome, valor in zip(INTEGRANTES, ["sim", "não", "incerto"]):
        alterar(pasta, nome, {("releases_reais", repo_empate, ""): valor})
    decisoes = {
        ("releases_reais", repo_empate, ""): {
            "rotulo": "não",
            "observacao": "decisão baseada nos commits",
        },
        ("releases_reais", repo_maioria, ""): {
            "rotulo": "sim",
            "observacao": "não deve substituir a maioria",
        },
    }

    consenso, reuniao = construir_consenso(carregar_rotulos(pasta, INTEGRANTES), decisoes)

    empate = linha(consenso, "releases_reais", repo_empate)
    maioria = linha(consenso, "releases_reais", repo_maioria)
    assert (empate["rotulo_consenso"], empate["decidido_em"]) == ("não", "reuniao")
    assert (maioria["rotulo_consenso"], maioria["decidido_em"]) == (
        rotulo_padrao("releases_reais", repo_maioria, ""),
        "maioria",
    )
    assert len(reuniao) == 1
    assert reuniao.iloc[0]["repo"] == repo_empate


# --------------------------------------------------------------------------
# Linha de comando: fluxo completo com a reunião
# --------------------------------------------------------------------------
def rodar(monkeypatch, pasta):
    monkeypatch.setattr("sys.argv", ["consenso.py", "--integrantes", *INTEGRANTES, "--pasta", str(pasta)])
    main()


def test_cli_sem_empates_grava_consenso_completo(pasta, monkeypatch, capsys):
    rodar(monkeypatch, pasta)

    consenso = ler_csv(pasta / ARQUIVO_CONSENSO)
    assert list(consenso.columns) == CAMPOS_CONSENSO
    assert set(consenso["decidido_em"]) == {"maioria"}
    assert (consenso["rotulo_consenso"] != "").all()
    assert "Consenso completo" in capsys.readouterr().out
    assert ler_csv(pasta / ARQUIVO_DECISOES).empty


def test_cli_fluxo_com_1_1_1_primeira_rodada_pendente_segunda_completa(pasta, monkeypatch, capsys):
    repo, _ = um_item(pasta)
    for nome, valor in zip(INTEGRANTES, ["sim", "não", "incerto"]):
        alterar(pasta, nome, {("releases_reais", repo, ""): valor})

    with pytest.raises(SystemExit, match="1 caso.*aguardam decisão da reunião"):  # 1ª rodada
        rodar(monkeypatch, pasta)
    decisoes = ler_csv(pasta / ARQUIVO_DECISOES)
    assert len(decisoes) == 1 and decisoes.loc[0, "rotulo_reuniao"] == ""
    assert (ler_csv(pasta / ARQUIVO_CONSENSO)["decidido_em"] == "reuniao").sum() == 1

    decisoes.loc[0, "rotulo_reuniao"] = "Não"  # decisão da reunião
    decisoes.loc[0, "observacao"] = "release = snapshot"
    decisoes.to_csv(pasta / ARQUIVO_DECISOES, index=False)

    rodar(monkeypatch, pasta)  # 2ª rodada
    consenso = ler_csv(pasta / ARQUIVO_CONSENSO)
    item = linha(consenso, "releases_reais", repo)
    assert (item["rotulo_consenso"], item["decidido_em"]) == ("não", "reuniao")
    assert (consenso["rotulo_consenso"] != "").all()
    assert "Consenso completo" in capsys.readouterr().out
    # a decisão continua registrada no arquivo da reunião
    assert ler_csv(pasta / ARQUIVO_DECISOES).loc[0, "observacao"] == "release = snapshot"


def test_cli_rodar_de_novo_preserva_decisoes_ja_tomadas(pasta, monkeypatch):
    repo, _ = um_item(pasta)
    for nome, valor in zip(INTEGRANTES, ["sim", "não", "incerto"]):
        alterar(pasta, nome, {("releases_reais", repo, ""): valor})
    with pytest.raises(SystemExit):
        rodar(monkeypatch, pasta)
    decisoes = ler_csv(pasta / ARQUIVO_DECISOES)
    decisoes.loc[0, "rotulo_reuniao"] = "sim"
    decisoes.to_csv(pasta / ARQUIVO_DECISOES, index=False)

    rodar(monkeypatch, pasta)
    rodar(monkeypatch, pasta)

    assert ler_csv(pasta / ARQUIVO_DECISOES).loc[0, "rotulo_reuniao"] == "sim"


def test_cli_decisao_com_rotulo_invalido_nao_gera_consenso(pasta, monkeypatch):
    escrever_decisoes(pasta, [["releases_reais", "org000/proj000", "", "x", "talvez", ""]])

    with pytest.raises(SystemExit, match="Consenso não calculado"):
        rodar(monkeypatch, pasta)
    assert not (pasta / ARQUIVO_CONSENSO).exists()


def test_cli_nao_calcula_consenso_com_planilha_incompleta(pasta, monkeypatch):
    preencher(pasta, "bruno", lambda d, r, t: "" if d == "tipo_projeto" else rotulo_padrao(d, r, t))

    with pytest.raises(SystemExit, match="Consenso não calculado"):
        rodar(monkeypatch, pasta)
    assert not (pasta / ARQUIVO_CONSENSO).exists()
