import csv
import json
import re
from pathlib import Path

import pytest

from coleta_releases import processar_repo
from conftest import (
    REPO,
    ClienteFalso,
    caminho_compare,
    caminho_releases,
    commit,
    compare,
    release,
)
from variantes import (
    CAMPOS_RESUMO,
    CAMPOS_TAGS,
    consulta_datas,
    datar_tags,
    datas_dos_commits,
    executar,
    lead_time_c2,
)

FIXTURES = Path(__file__).parent / "fixtures"


def sha(n: int) -> str:
    """Sha de 40 caracteres hexadecimais; a ordem de n é a ordem alfabética."""
    return f"{n:040x}"


def tag(nome: str, sha_commit: str) -> dict:
    return {"full_name": REPO, "tag_name": nome, "sha": sha_commit}


class ClienteGraphqlFalso(ClienteFalso):
    """ClienteFalso (REST, por caminho e página) que também simula GitHubClient.graphql para a
    consulta de datas: responde com as datas de `datas` ({sha: data}; None = objeto que não é
    commit) e registra os shas de cada consulta em `consultas`. `resposta_fixa` ignora a
    consulta e devolve sempre (200, resposta_fixa)."""

    def __init__(self, datas=None, status=200, resposta_fixa=None, respostas=None):
        super().__init__(respostas or {})
        self.datas = datas or {}
        self.status = status
        self.resposta_fixa = resposta_fixa
        self.consultas = []
        self.cache_hits = 0

    def graphql(self, query, variables=None, versao_cache=None):
        shas = re.findall(r'c\d+: object\(oid: "([0-9a-f]{40})"\)', query)
        self.consultas.append((shas, variables))
        if self.resposta_fixa is not None:
            return 200, self.resposta_fixa
        if self.status != 200:
            return self.status, {"message": "erro"}
        repositorio = {}
        for i, s in enumerate(shas):
            if s not in self.datas:
                repositorio[f"c{i}"] = None                       # sha inexistente
            elif self.datas[s] is None:
                repositorio[f"c{i}"] = {}                         # objeto que não é commit
            else:
                repositorio[f"c{i}"] = {"committedDate": self.datas[s]}
        return 200, {"data": {"repository": repositorio}}


# --------------------------------------------------------------------------
# Release + pré-release (C2)
# --------------------------------------------------------------------------
def status_por_tag(linhas):
    return {linha["tag_name"]: linha["status"] for linha in linhas}


def test_sem_pre_releases_a_c2_da_o_mesmo_resultado_da_definicao_principal(cliente, janela, releases_v1_0_e_v1_1):
    respostas = {
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(
            commit("a", "2026-03-02T00:00:00Z"),
            commit("b", "2026-03-10T00:00:00Z"),
            commit("c", "2026-03-14T00:00:00Z"),
        ),
    }

    principal = processar_repo(cliente(respostas), REPO, *janela)["resumo"]
    linhas, c2 = lead_time_c2(cliente(respostas), REPO, *janela)

    assert status_por_tag(linhas) == {"v1.0": "primeira_release", "v1.1": "ok"}
    assert next(r for r in linhas if r["tag_name"] == "v1.1")["lead_time_release_dias"] == 13
    assert c2["releases_calculadas_c2"] == principal["releases_calculadas"]
    assert c2["lead_time_release_mediana_dias_c2"] == principal["lead_time_release_mediana_dias"] == 13
    assert c2["lead_time_commit_mediana_dias_c2"] == principal["lead_time_commit_mediana_dias"] == 5


def test_pre_release_entre_duas_releases_muda_os_pares(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.1-rc1", "2026-03-08T00:00:00Z", prerelease=True),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.0", "v1.1-rc1"), 1): compare(commit("a", "2026-03-02T00:00:00Z")),
        (caminho_compare("v1.1-rc1", "v1.1"), 1): compare(
            commit("b", "2026-03-10T00:00:00Z"),
            commit("c", "2026-03-14T00:00:00Z"),
        ),
    })

    linhas, resumo = lead_time_c2(api, REPO, *janela)

    assert [(r["tag_name"], r["tag_anterior"], r["prerelease"]) for r in linhas] == [
        ("v1.0", "", False),
        ("v1.1-rc1", "v1.0", True),
        ("v1.1", "v1.1-rc1", False),
    ]
    assert [r["lead_time_release_dias"] for r in linhas] == ["", 6, 5]
    assert resumo["lead_time_release_mediana_dias_c2"] == 5.5     # mediana de 6 e 5
    assert resumo["lead_time_commit_mediana_dias_c2"] == 5        # mediana de 6, 5 e 1
    assert (caminho_compare("v1.0", "v1.1"), 1) not in api.chamadas


def test_draft_fica_fora_da_c2(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v1.1", "2026-03-15T00:00:00Z"),
            release("v1.1-draft", "2026-03-10T00:00:00Z", draft=True),
            release("v1.0", "2026-03-01T00:00:00Z"),
        ], None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z")),
    })

    linhas, _ = lead_time_c2(api, REPO, *janela)

    assert status_por_tag(linhas) == {"v1.0": "primeira_release", "v1.1": "ok"}


def test_pre_release_anterior_a_janela_serve_de_base_mas_nao_entra_no_calculo(cliente, janela):
    api = cliente({
        (caminho_releases(), 1): (200, [
            release("v2.0", "2025-10-05T00:00:00Z"),
            release("v2.0-rc1", "2025-09-25T00:00:00Z", prerelease=True),
            release("v1.9", "2025-09-01T00:00:00Z"),
        ], None),
        (caminho_compare("v2.0-rc1", "v2.0"), 1): compare(commit("a", "2025-10-01T00:00:00Z")),
    })

    linhas, resumo = lead_time_c2(api, REPO, *janela)

    assert [(r["tag_name"], r["tag_anterior"], r["status"]) for r in linhas] == [("v2.0", "v2.0-rc1", "ok")]
    assert resumo["releases_na_janela_c2"] == 1


def test_tag_404_na_c2_pula_a_release_e_conta(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({(caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None)})

    linhas, resumo = lead_time_c2(api, REPO, *janela)

    assert status_por_tag(linhas)["v1.1"] == "tag_404"
    assert resumo["releases_404_c2"] == 1
    assert resumo["lead_time_release_mediana_dias_c2"] == ""


def test_outro_erro_no_compare_da_c2_e_contado_separado_do_404(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): (500, None, None),
    })

    linhas, resumo = lead_time_c2(api, REPO, *janela)

    assert status_por_tag(linhas)["v1.1"] == "erro_http_500"
    assert (resumo["releases_erro_c2"], resumo["releases_404_c2"]) == (1, 0)


def test_release_sem_commits_novos_na_c2_fica_sem_lead_time(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(),
    })

    linhas, resumo = lead_time_c2(api, REPO, *janela)

    assert status_por_tag(linhas)["v1.1"] == "sem_commits"
    assert resumo["releases_sem_commits_c2"] == 1


def test_compare_incompleto_e_lead_time_negativo_sao_contados(cliente, janela, releases_v1_0_e_v1_1):
    api = cliente({
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-16T00:00:00Z"), total=300),
    })

    _, resumo = lead_time_c2(api, REPO, *janela)

    assert resumo["releases_commits_incompletos_c2"] == 1
    assert resumo["commits_lead_time_negativo_c2"] == 1


def test_erro_ao_listar_releases_vira_status_da_c2(cliente, janela):
    api = cliente({(caminho_releases(), 1): (403, {"message": "Forbidden"}, None)})

    linhas, resumo = lead_time_c2(api, REPO, *janela)

    assert linhas == []
    assert resumo["status_releases_c2"] == "erro_http_403"


# --------------------------------------------------------------------------
# Datas das tags (C3)
# --------------------------------------------------------------------------
def test_resposta_graphql_fixa_preenche_commit_date():
    resposta = json.loads((FIXTURES / "graphql_datas_tags.json").read_text(encoding="utf-8"))
    api = ClienteGraphqlFalso(resposta_fixa=resposta)
    tags = [
        tag("v2.0", sha(1)),       # c0
        tag("v1.0", sha(2)),       # c1
        tag("v2.0-final", sha(1)), # mesmo commit da v2.0
        tag("apagada", sha(3)),    # c2: sha que não existe mais
    ]

    linhas, resumo = datar_tags(api, REPO, tags)

    assert [(t["tag_name"], t["commit_date"]) for t in linhas] == [
        ("v2.0", "2026-03-15T12:00:00Z"),
        ("v1.0", "2025-09-01T08:30:00Z"),
        ("v2.0-final", "2026-03-15T12:00:00Z"),
        ("apagada", ""),
    ]
    assert resumo == {"status_tags_datas": "ok", "tags": 4, "tags_sem_data": 1}
    assert len(api.consultas) == 1


def test_consulta_tem_um_alias_por_sha_e_usa_variaveis_para_o_repositorio():
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z"})

    datas_dos_commits(api, REPO, [sha(1)])

    shas, variaveis = api.consultas[0]
    assert shas == [sha(1)]
    assert variaveis == {"owner": "org", "name": "projeto"}
    assert "$owner: String!" in consulta_datas([sha(1)])


def test_tags_no_mesmo_commit_geram_uma_consulta_so():
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z"})

    datar_tags(api, REPO, [tag("v1", sha(1)), tag("v1-lts", sha(1)), tag("latest", sha(1))])

    assert api.consultas[0][0] == [sha(1)]


def test_shas_sao_consultados_em_lotes_de_100_e_em_ordem_fixa():
    datas = {sha(n): "2026-01-01T00:00:00Z" for n in range(150)}
    api = ClienteGraphqlFalso(datas)
    tags = [tag(f"v{n}", sha(n)) for n in reversed(range(150))]

    _, resumo = datar_tags(api, REPO, tags)

    assert [len(shas) for shas, _ in api.consultas] == [100, 50]
    assert api.consultas[0][0] == sorted(api.consultas[0][0])
    assert resumo["tags_sem_data"] == 0


def test_objeto_que_nao_e_commit_fica_sem_data():
    api = ClienteGraphqlFalso({sha(1): None})

    linhas, resumo = datar_tags(api, REPO, [tag("arvore", sha(1))])

    assert linhas[0]["commit_date"] == ""
    assert resumo["tags_sem_data"] == 1


def test_sha_invalido_nao_entra_na_consulta():
    api = ClienteGraphqlFalso()

    linhas, resumo = datar_tags(api, REPO, [tag("estranha", 'abc") { x }')])

    assert api.consultas == []
    assert linhas[0]["commit_date"] == ""
    assert (resumo["status_tags_datas"], resumo["tags_sem_data"]) == ("ok", 1)


def test_repositorio_sem_tags_nao_chama_a_api():
    api = ClienteGraphqlFalso()

    linhas, resumo = datar_tags(api, REPO, [])

    assert (linhas, api.consultas) == ([], [])
    assert (resumo["status_tags_datas"], resumo["tags"]) == ("ok", 0)


def test_repositorio_inexistente_vira_status_e_mantem_as_tags():
    resposta = {"data": {"repository": None}, "errors": [{"type": "NOT_FOUND", "message": "Could not resolve"}]}
    api = ClienteGraphqlFalso(resposta_fixa=resposta)

    linhas, resumo = datar_tags(api, REPO, [tag("v1", sha(1))])

    assert resumo["status_tags_datas"] == "erro_graphql_NOT_FOUND"
    assert [t["commit_date"] for t in linhas] == [""]


def test_erro_http_vira_status_sem_derrubar_o_repositorio():
    api = ClienteGraphqlFalso(status=403)

    linhas, resumo = datar_tags(api, REPO, [tag("v1", sha(1))])

    assert resumo["status_tags_datas"] == "erro_http_403"
    assert len(linhas) == 1


# --------------------------------------------------------------------------
# Etapa: lê o tags.csv da etapa releases e regrava com commit_date
# --------------------------------------------------------------------------
def gravar_tags_csv(pasta: Path, linhas: list[dict], campos=("full_name", "tag_name", "sha")):
    with (pasta / "tags.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(campos), extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def ler_csv(caminho: Path) -> list[dict]:
    with caminho.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_executar_regrava_tags_csv_com_commit_date_e_grava_o_resumo(janela, tmp_path):
    gravar_tags_csv(tmp_path, [tag("v1", sha(1)), tag("v2", sha(2))])
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z", sha(2): "2026-02-01T00:00:00Z"})

    executar(api, *janela, [{"full_name": REPO}], tmp_path)

    tags = ler_csv(tmp_path / "tags.csv")
    assert list(tags[0]) == CAMPOS_TAGS
    assert [t["commit_date"] for t in tags] == ["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"]
    resumo = ler_csv(tmp_path / "variantes_repos.csv")
    assert [(r["full_name"], r["status_tags_datas"], r["tags"], r["tags_sem_data"]) for r in resumo] == [
        (REPO, "ok", "2", "0")
    ]


def test_executar_duas_vezes_da_o_mesmo_tags_csv(janela, tmp_path):
    gravar_tags_csv(tmp_path, [tag("v1", sha(1))])
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z"})

    executar(api, *janela, [{"full_name": REPO}], tmp_path)
    primeira = (tmp_path / "tags.csv").read_text(encoding="utf-8")
    executar(api, *janela, [{"full_name": REPO}], tmp_path)

    assert (tmp_path / "tags.csv").read_text(encoding="utf-8") == primeira


def test_executar_mantem_as_tags_de_repositorios_fora_da_lista(janela, tmp_path):
    outra = {"full_name": "org/outro", "tag_name": "v9", "sha": sha(9), "commit_date": "2026-05-05T00:00:00Z"}
    gravar_tags_csv(tmp_path, [tag("v1", sha(1)), outra], campos=CAMPOS_TAGS)
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z"})

    executar(api, *janela, [{"full_name": REPO}], tmp_path)

    tags = ler_csv(tmp_path / "tags.csv")
    assert tags[-1] == outra
    assert [shas for shas, _ in api.consultas] == [[sha(1)]]


def test_executar_grava_releases_c2_e_junta_c2_e_tags_no_resumo(janela, tmp_path, releases_v1_0_e_v1_1):
    gravar_tags_csv(tmp_path, [tag("v1.1", sha(1))])
    api = ClienteGraphqlFalso({sha(1): "2026-03-14T00:00:00Z"}, respostas={
        (caminho_releases(), 1): (200, releases_v1_0_e_v1_1, None),
        (caminho_compare("v1.0", "v1.1"), 1): compare(commit("a", "2026-03-02T00:00:00Z")),
    })

    executar(api, *janela, [{"full_name": REPO}], tmp_path)

    releases_c2 = ler_csv(tmp_path / "releases_c2.csv")
    assert [(r["tag_name"], r["status"], r["lead_time_release_dias"]) for r in releases_c2] == [
        ("v1.0", "primeira_release", ""),
        ("v1.1", "ok", "13.0"),
    ]
    resumo = ler_csv(tmp_path / "variantes_repos.csv")
    assert list(resumo[0]) == CAMPOS_RESUMO
    assert (resumo[0]["releases_calculadas_c2"], resumo[0]["tags"]) == ("1", "1")


def test_executar_sem_tags_csv_pede_a_etapa_releases(janela, tmp_path):
    with pytest.raises(SystemExit, match="etapa releases"):
        executar(ClienteGraphqlFalso(), *janela, [{"full_name": REPO}], tmp_path)
