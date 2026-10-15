"""Validação das planilhas de rótulos: completas, só valores permitidos, consistentes."""

import pytest

from dados_validacao import INTEGRANTES, preencher, rotulo_padrao, sortear_e_gravar
from validar_rotulos import (
    RotulosInvalidos,
    carregar_rotulos,
    ler_amostra,
    ler_csv,
    main,
    normalizar_valor,
    tabela_itens,
    validar_planilha,
    validar_todas,
)


@pytest.fixture
def pasta(tmp_path):
    """Pasta com o sorteio gravado e as três planilhas preenchidas corretamente."""
    sortear_e_gravar(tmp_path)
    for nome in INTEGRANTES:
        preencher(tmp_path, nome, rotulo_padrao)
    return tmp_path


def erros_da(pasta, nome="ana"):
    return validar_planilha(ler_csv(pasta / f"rotulos_{nome}.csv"), ler_amostra(pasta))


def editar(pasta, nome, funcao):
    """Aplica `funcao(df)` à planilha do integrante e grava de volta."""
    caminho = pasta / f"rotulos_{nome}.csv"
    df = ler_csv(caminho)
    funcao(df)
    df.to_csv(caminho, index=False, encoding="utf-8-sig")


# --------------------------------------------------------------------------
# Planilha completa e válida
# --------------------------------------------------------------------------
def test_planilhas_completas_sao_validas(pasta):
    assert validar_todas(pasta, INTEGRANTES) == {}


def test_planilha_recem_gerada_esta_incompleta(tmp_path):
    sortear_e_gravar(tmp_path)

    erros = erros_da(tmp_path)

    assert len(erros) == 40 * 3  # 8 repositórios x 5 releases x 3 colunas vazias
    assert "linha 2: coluna 'tipo_projeto' vazia" in erros


# --------------------------------------------------------------------------
# Células vazias e valores fora do permitido
# --------------------------------------------------------------------------
def test_celula_vazia_e_apontada_com_o_numero_da_linha(pasta):
    def esvaziar(df):
        df.loc[4, "corretiva"] = ""

    editar(pasta, "ana", esvaziar)

    assert erros_da(pasta) == ["linha 6: coluna 'corretiva' vazia"]  # índice 4 = linha 6 da planilha


def test_celula_so_com_espacos_conta_como_vazia(pasta):
    def so_espacos(df):
        df.loc[0, "corretiva"] = "   "

    editar(pasta, "ana", so_espacos)

    assert erros_da(pasta) == ["linha 2: coluna 'corretiva' vazia"]


@pytest.mark.parametrize(("coluna", "valor"), [
    ("tipo_projeto", "biblioteca"),
    ("tipo_projeto", "app"),
    ("releases_reais", "talvez"),
    ("corretiva", "incerto"),  # incerto só vale para releases_reais
    ("corretiva", "talvez"),
])
def test_valor_fora_do_permitido_e_rejeitado(pasta, coluna, valor):
    editar(pasta, "bruno", lambda df: df.__setitem__(coluna, [valor] * len(df)))

    erros = erros_da(pasta, "bruno")

    assert any(f"valor '{valor}' inválido em '{coluna}'" in e for e in erros)


def test_mensagem_de_valor_invalido_lista_os_permitidos(pasta):
    editar(pasta, "ana", lambda df: df.__setitem__("corretiva", ["talvez"] + list(df["corretiva"][1:])))

    assert "permitidos: sim, não" in erros_da(pasta)[0]


@pytest.mark.parametrize(("dimensao", "digitado", "canonico"), [
    ("corretiva", "SIM", "sim"),
    ("corretiva", " nao ", "não"),
    ("releases_reais", "Incerto", "incerto"),
    ("tipo_projeto", "aplicacao/servico", "aplicação/serviço"),
    ("tipo_projeto", "Ferramenta  cli", "ferramenta CLI"),
    ("tipo_projeto", "BIBLIOTECA/FRAMEWORK", "biblioteca/framework"),
    ("tipo_projeto", "Outro", "outro"),
])
def test_maiusculas_acentos_e_espacos_sao_tolerados_e_normalizados(dimensao, digitado, canonico):
    assert normalizar_valor(dimensao, digitado) == canonico


@pytest.mark.parametrize("dimensao", ["tipo_projeto", "releases_reais", "corretiva"])
def test_vazio_e_desconhecido_nao_normalizam(dimensao):
    assert normalizar_valor(dimensao, "") is None
    assert normalizar_valor(dimensao, "xyz") is None


def test_valores_digitados_de_outro_jeito_viram_o_canonico_ao_carregar(pasta):
    editar(pasta, "ana", lambda df: df.__setitem__("corretiva", ["NAO" if v == "não" else "Sim" for v in df["corretiva"]]))

    rotulos = carregar_rotulos(pasta, INTEGRANTES)

    assert set(rotulos["ana"]["corretiva"]) == {"sim", "não"}


# --------------------------------------------------------------------------
# Consistência por repositório
# --------------------------------------------------------------------------
def test_tipo_projeto_diferente_nas_linhas_do_mesmo_repositorio_e_erro(pasta):
    editar(pasta, "carla", lambda df: df.__setitem__(
        "tipo_projeto", ["outro" if i == 0 else v for i, v in enumerate(df["tipo_projeto"])]))

    erros = erros_da(pasta, "carla")

    assert len(erros) == 1
    assert "'tipo_projeto' tem valores diferentes nas linhas de org" in erros[0]


def test_releases_reais_diferente_nas_linhas_do_mesmo_repositorio_e_erro(pasta):
    editar(pasta, "carla", lambda df: df.__setitem__(
        "releases_reais", ["incerto" if i == 1 else v for i, v in enumerate(df["releases_reais"])]))

    assert any("'releases_reais' tem valores diferentes" in e for e in erros_da(pasta, "carla"))


def test_corretiva_pode_variar_entre_as_releases_do_mesmo_repositorio(pasta):
    assert erros_da(pasta) == []  # rotulo_padrao varia corretiva dentro do repositório


# --------------------------------------------------------------------------
# Linhas e colunas
# --------------------------------------------------------------------------
def test_linha_faltando_e_apontada(pasta):
    editar(pasta, "ana", lambda df: df.drop(index=3, inplace=True))
    df = ler_csv(pasta / "rotulos_ana.csv")

    erros = erros_da(pasta)

    assert len(df) == 39
    assert len(erros) == 1 and erros[0].startswith("linha faltando: org")


def test_linha_que_nao_foi_sorteada_e_apontada(pasta):
    def inventar(df):
        df.loc[0, "tag"] = "v9.9"

    editar(pasta, "ana", inventar)

    erros = erros_da(pasta)

    assert any(e.startswith("linha que não está na amostra sorteada") and "v9.9" in e for e in erros)
    assert any(e.startswith("linha faltando") for e in erros)


def test_release_repetida_e_apontada(pasta):
    def repetir(df):
        for coluna in df.columns:
            df.loc[1, coluna] = df.loc[0, coluna]

    editar(pasta, "ana", repetir)

    assert any(e.startswith("release repetida") for e in erros_da(pasta))


def test_coluna_ausente_e_apontada(pasta):
    editar(pasta, "ana", lambda df: df.drop(columns=["corretiva"], inplace=True))

    assert erros_da(pasta) == ["colunas ausentes: corretiva"]


def test_planilha_inexistente_e_apontada(pasta):
    (pasta / "rotulos_carla.csv").unlink()

    assert validar_todas(pasta, INTEGRANTES) == {"carla": ["arquivo rotulos_carla.csv não existe"]}


def test_sem_amostra_ouro_o_erro_manda_rodar_o_sorteio(tmp_path):
    with pytest.raises(FileNotFoundError, match="amostra_ouro.py"):
        validar_todas(tmp_path, INTEGRANTES)


# --------------------------------------------------------------------------
# Formato do arquivo
# --------------------------------------------------------------------------
def test_aceita_ponto_e_virgula_do_excel_em_portugues(pasta):
    caminho = pasta / "rotulos_ana.csv"
    texto = caminho.read_text(encoding="utf-8-sig")
    caminho.write_text(texto.replace(",", ";"), encoding="utf-8-sig")

    assert validar_todas(pasta, INTEGRANTES) == {}


def test_aceita_arquivo_com_e_sem_bom(pasta):
    caminho = pasta / "rotulos_bruno.csv"
    caminho.write_text(caminho.read_text(encoding="utf-8-sig"), encoding="utf-8")  # sem BOM

    assert validar_todas(pasta, INTEGRANTES) == {}


# --------------------------------------------------------------------------
# carregar_rotulos, tabela_itens e linha de comando
# --------------------------------------------------------------------------
def test_carregar_rotulos_de_planilhas_invalidas_levanta_com_o_relatorio(pasta):
    editar(pasta, "ana", lambda df: df.__setitem__("corretiva", [""] * len(df)))

    with pytest.raises(RotulosInvalidos, match="rotulos_ana.csv: 40 problema") as exc:
        carregar_rotulos(pasta, INTEGRANTES)
    assert set(exc.value.erros) == {"ana"}


def test_relatorio_limita_a_quantidade_de_mensagens_por_planilha(tmp_path):
    sortear_e_gravar(tmp_path)

    with pytest.raises(RotulosInvalidos, match=r"\.\.\. e mais 105"):
        carregar_rotulos(tmp_path, INTEGRANTES)


def test_tabela_itens_tem_um_item_por_repositorio_ou_por_release(pasta):
    rotulos = carregar_rotulos(pasta, INTEGRANTES)

    repo_level = tabela_itens(rotulos, "tipo_projeto")
    release_level = tabela_itens(rotulos, "corretiva")

    assert repo_level.shape == (8, 3) and set(repo_level.index.get_level_values("tag")) == {""}
    assert release_level.shape == (40, 3) and "" not in set(release_level.index.get_level_values("tag"))
    assert list(release_level.columns) == INTEGRANTES


def test_cli_ok_e_cli_com_erro(pasta, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["validar_rotulos.py", "--integrantes", *INTEGRANTES, "--pasta", str(pasta)])
    main()
    assert "OK: 3 planilhas completas" in capsys.readouterr().out

    editar(pasta, "ana", lambda df: df.__setitem__("corretiva", [""] * len(df)))
    with pytest.raises(SystemExit) as saida:
        main()
    assert saida.value.code == 1
    assert "rotulos_ana.csv" in capsys.readouterr().err
