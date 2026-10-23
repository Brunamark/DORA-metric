import csv

import pytest

from avaliar_heuristica import (
    avaliar,
    executar,
    ler_consenso,
    normalizar_rotulo,
    prf,
    prf_manual,
    tabela_markdown,
)
from metricas import CRITERIOS, PAREAMENTOS


def exemplo_enunciado():
    """Heurística marca 40, consenso confirma 30; consenso tem 50 corretivas (P=75%, R=60%)."""
    y_true = [True] * 30 + [False] * 10 + [True] * 20 + [False] * 40
    y_pred = [True] * 30 + [True] * 10 + [False] * 20 + [False] * 40
    return y_true, y_pred


def test_exemplo_do_enunciado_manual():
    p, r, f1 = prf_manual(*exemplo_enunciado())

    assert (p, r) == (0.75, 0.6)
    assert f1 == pytest.approx(2 * 0.75 * 0.6 / 1.35)


def test_prf_usa_sklearn_ou_manual_com_o_mesmo_resultado():
    for obtido, esperado in zip(prf(*exemplo_enunciado()), prf_manual(*exemplo_enunciado())):
        assert obtido == pytest.approx(esperado)


def test_prf_sem_positivos_da_zero():
    assert prf_manual([False, False], [False, False]) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("valor, esperado", [
    ("sim", True), ("Sim", True), (" S ", True), ("yes", True), ("1", True),
    ("não", False), ("Não", False), ("nao", False), ("N", False), ("false", False),
    ("incerto", None), ("", None), (None, None),
])
def test_normalizar_rotulo(valor, esperado):
    assert normalizar_rotulo(valor) is esperado


def test_consenso_detecta_a_coluna_e_descarta_incertos():
    linhas = [
        {"full_name": "o/r", "tag_name": "v1", "corretiva_consenso": "sim"},
        {"full_name": "o/r", "tag_name": "v2", "corretiva_consenso": "incerto"},
        {"full_name": "o/r", "tag_name": "v3", "corretiva_consenso": "não"},
    ]

    rotulos, descartados = ler_consenso(linhas)

    assert rotulos == {("o/r", "v1"): True, ("o/r", "v3"): False}
    assert descartados == 1


def test_consenso_no_formato_longo_usa_so_a_dimensao_corretiva():
    linhas = [
        {"dimensao": "tipo_projeto", "repo": "o/r", "tag": "v1", "votos": "", "rotulo_consenso": "não", "decidido_em": "maioria"},
        {"dimensao": "corretiva", "repo": "o/r", "tag": "v1", "votos": "", "rotulo_consenso": "sim", "decidido_em": "maioria"},
        {"dimensao": "corretiva", "repo": "o/r", "tag": "v2", "votos": "", "rotulo_consenso": "", "decidido_em": "reuniao"},
    ]

    rotulos, descartados = ler_consenso(linhas)

    assert rotulos == {("o/r", "v1"): True}
    assert descartados == 1


def test_planilha_de_rotulagem_com_repo_e_tag():
    linhas = [
        {"repo": "o/r", "tag": "v1", "tag_anterior": "v0", "tipo_projeto": "sim", "releases_reais": "sim", "corretiva": "não"},
        {"repo": "o/r", "tag": "v2", "tag_anterior": "v1", "tipo_projeto": "sim", "releases_reais": "sim", "corretiva": "sim"},
    ]

    rotulos, descartados = ler_consenso(linhas)

    assert rotulos == {("o/r", "v1"): False, ("o/r", "v2"): True}
    assert descartados == 0


def carac(tag, pareamento, **corretivas):
    linha = {"full_name": "o/r", "tag_name": tag, "pareamento": pareamento, "tipo_mudanca": "patch",
             "predecessora": "v0", "n_commits": "1", "n_fix": "1"}
    for c in CRITERIOS:
        linha[f"corretiva_{c}"] = corretivas.get(c, "nao")
    return linha


def test_avaliar_conta_acertos_erros_e_indeterminadas():
    rotulos = {("o/r", "v1"): True, ("o/r", "v2"): False, ("o/r", "v3"): True, ("o/r", "fantasma"): True}
    caracteristicas = []
    for p in PAREAMENTOS:
        caracteristicas += [
            carac("v1", p, semver_e_mensagem="sim"),      # VP
            carac("v2", p, semver_e_mensagem="sim"),      # FP
            carac("v3", p, semver_e_mensagem=""),         # indeterminada -> FN
        ]

    avaliacao, erros, sem_carac = avaliar(rotulos, caracteristicas)

    v1 = next(a for a in avaliacao if a["versao"] == "linha/semver_e_mensagem")
    assert (v1["n"], v1["vp"], v1["fp"], v1["fn"], v1["vn"], v1["indeterminadas"]) == (3, 1, 1, 1, 0, 1)
    assert (v1["precisao"], v1["recall"], v1["f1"]) == (0.5, 0.5, 0.5)
    assert sem_carac == 1
    assert {e["erro"] for e in erros if e["versao"] == "linha/semver_e_mensagem"} == {"falso_positivo", "falso_negativo"}
    assert len(avaliacao) == len(PAREAMENTOS) * len(CRITERIOS)
    assert avaliacao == sorted(avaliacao, key=lambda a: (-a["f1"], a["versao"]))


def test_tabela_markdown_tem_uma_linha_por_versao():
    avaliacao, _, _ = avaliar({("o/r", "v1"): True}, [carac("v1", "linha", semver_e_mensagem="sim")])

    assert len(tabela_markdown(avaliacao).splitlines()) == 2 + len(avaliacao)


def escrever(caminho, linhas):
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)


def test_executar_grava_as_tres_saidas(tmp_path):
    escrever(tmp_path / "consenso.csv", [{"full_name": "o/r", "tag_name": "v1", "corretiva": "sim"}])
    escrever(tmp_path / "carac.csv", [carac("v1", p, semver_e_mensagem="sim") for p in PAREAMENTOS])

    avaliacao = executar(tmp_path / "consenso.csv", tmp_path / "carac.csv", tmp_path / "saida")

    assert avaliacao[0]["f1"] == 1.0
    for nome in ("avaliacao_heuristica.csv", "avaliacao_heuristica.md", "erros_heuristica.csv"):
        assert (tmp_path / "saida" / nome).exists()
