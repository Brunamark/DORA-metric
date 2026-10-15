import csv
import json
import re
from pathlib import Path

import pytest

from conftest import REPO
from variantes import CAMPOS_TAGS, consulta_datas, datar_tags, datas_dos_commits, executar

FIXTURES = Path(__file__).parent / "fixtures"


def sha(n: int) -> str:
    """Sha de 40 caracteres hexadecimais; a ordem de n é a ordem alfabética."""
    return f"{n:040x}"


def tag(nome: str, sha_commit: str) -> dict:
    return {"full_name": REPO, "tag_name": nome, "sha": sha_commit}


class ClienteGraphqlFalso:
    """Simula GitHubClient.graphql para a consulta de datas: responde com as datas de
    `datas` ({sha: data}; None = objeto que não é commit) e registra os shas de cada chamada.
    `resposta_fixa` ignora a consulta e devolve sempre (200, resposta_fixa)."""

    def __init__(self, datas=None, status=200, resposta_fixa=None):
        self.datas = datas or {}
        self.status = status
        self.resposta_fixa = resposta_fixa
        self.chamadas = []
        self.cache_hits = 0

    def graphql(self, query, variables=None, versao_cache=None):
        shas = re.findall(r'c\d+: object\(oid: "([0-9a-f]{40})"\)', query)
        self.chamadas.append((shas, variables))
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
    assert resumo == {"full_name": REPO, "status_tags_datas": "ok", "tags": 4, "tags_sem_data": 1}
    assert len(api.chamadas) == 1


def test_consulta_tem_um_alias_por_sha_e_usa_variaveis_para_o_repositorio():
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z"})

    datas_dos_commits(api, REPO, [sha(1)])

    shas, variaveis = api.chamadas[0]
    assert shas == [sha(1)]
    assert variaveis == {"owner": "org", "name": "projeto"}
    assert "$owner: String!" in consulta_datas([sha(1)])


def test_tags_no_mesmo_commit_geram_uma_consulta_so():
    api = ClienteGraphqlFalso({sha(1): "2026-01-01T00:00:00Z"})

    datar_tags(api, REPO, [tag("v1", sha(1)), tag("v1-lts", sha(1)), tag("latest", sha(1))])

    assert api.chamadas[0][0] == [sha(1)]


def test_shas_sao_consultados_em_lotes_de_100_e_em_ordem_fixa():
    datas = {sha(n): "2026-01-01T00:00:00Z" for n in range(150)}
    api = ClienteGraphqlFalso(datas)
    tags = [tag(f"v{n}", sha(n)) for n in reversed(range(150))]

    _, resumo = datar_tags(api, REPO, tags)

    assert [len(shas) for shas, _ in api.chamadas] == [100, 50]
    assert api.chamadas[0][0] == sorted(api.chamadas[0][0])
    assert resumo["tags_sem_data"] == 0


def test_objeto_que_nao_e_commit_fica_sem_data():
    api = ClienteGraphqlFalso({sha(1): None})

    linhas, resumo = datar_tags(api, REPO, [tag("arvore", sha(1))])

    assert linhas[0]["commit_date"] == ""
    assert resumo["tags_sem_data"] == 1


def test_sha_invalido_nao_entra_na_consulta():
    api = ClienteGraphqlFalso()

    linhas, resumo = datar_tags(api, REPO, [tag("estranha", 'abc") { x }')])

    assert api.chamadas == []
    assert linhas[0]["commit_date"] == ""
    assert (resumo["status_tags_datas"], resumo["tags_sem_data"]) == ("ok", 1)


def test_repositorio_sem_tags_nao_chama_a_api():
    api = ClienteGraphqlFalso()

    linhas, resumo = datar_tags(api, REPO, [])

    assert (linhas, api.chamadas) == ([], [])
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
    assert resumo == [{"full_name": REPO, "status_tags_datas": "ok", "tags": "2", "tags_sem_data": "0"}]


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
    assert [shas for shas, _ in api.chamadas] == [[sha(1)]]


def test_executar_sem_tags_csv_pede_a_etapa_releases(janela, tmp_path):
    with pytest.raises(SystemExit, match="etapa releases"):
        executar(ClienteGraphqlFalso(), *janela, [{"full_name": REPO}], tmp_path)
