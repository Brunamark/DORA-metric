"""Fixtures compartilhadas: dados pequenos montados à mão, com resultado conhecido."""

from datetime import datetime, timedelta, timezone

import pytest

from metricas import Run

REPO = "org/projeto"


def dia(mes: int, d: int, ano: int = 2026) -> datetime:
    return datetime(ano, mes, d, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Métricas: exemplo trabalhado da RQ 02 (v1.1 em 15/03, commits de 02/03, 10/03 e 14/03)
# --------------------------------------------------------------------------
@pytest.fixture
def data_v1_1():
    return dia(3, 15)


@pytest.fixture
def commits_v1_1():
    return [dia(3, 2), dia(3, 10), dia(3, 14)]


@pytest.fixture
def release_v1_1(data_v1_1, commits_v1_1):
    """(data da release, datas dos commits): 13, 5 e 1 dias de lead time."""
    return data_v1_1, commits_v1_1


@pytest.fixture
def release_com_commit_esquecido():
    """Release de 15/04 com três commits recentes e um esquecido desde 15/01."""
    return dia(4, 15), [dia(1, 15), dia(4, 14), dia(4, 13), dia(4, 12)]


# --------------------------------------------------------------------------
# Métricas: exemplo trabalhado da RQ 04 (workflow CI no main, episódio de 1h20)
# --------------------------------------------------------------------------
def hora(h: int, m: int = 0, d: int = 10) -> datetime:
    return datetime(2026, 3, d, h, m, tzinfo=timezone.utc)


def workflow_run(run_id, conclusao, inicio, fim=None, workflow_id=1, iniciado=True):
    """Run que começa em `inicio` e termina em `fim` (padrão: 5 min depois).
    `iniciado=False` simula run_started_at vazio na API."""
    return Run(
        id=run_id,
        workflow_id=workflow_id,
        conclusao=conclusao,
        criado_em=inicio,
        iniciado_em=inicio if iniciado else None,
        atualizado_em=fim or inicio + timedelta(minutes=5),
    )


@pytest.fixture
def runs_exemplo_rq04():
    """success 09:00 -> failure 10:00 -> failure 10:30 -> success 11:15 (terminou 11:20)."""
    return [
        workflow_run(1, "success", hora(9)),
        workflow_run(2, "failure", hora(10)),
        workflow_run(3, "failure", hora(10, 30)),
        workflow_run(4, "success", hora(11, 15), fim=hora(11, 20)),
    ]


# --------------------------------------------------------------------------
# Coleta: janela do estudo e cliente falso da API
# --------------------------------------------------------------------------
@pytest.fixture
def janela():
    return (
        datetime(2025, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 23, 59, 59, tzinfo=timezone.utc),
    )


class ClienteFalso:
    """Simula GitHubClient.get: respostas por (caminho, página) e registro das chamadas.
    Caminho sem resposta cadastrada devolve 404."""

    def __init__(self, respostas: dict):
        self.respostas = respostas
        self.chamadas = []

    def get(self, path, params=None, enxugar=None):
        pagina = (params or {}).get("page", 1)
        self.chamadas.append((path, pagina))
        status, corpo, link = self.respostas.get((path, pagina), (404, {"message": "Not Found"}, None))
        if enxugar and status == 200:
            corpo = enxugar(corpo)
        return status, corpo, link


@pytest.fixture
def cliente():
    """Fábrica: cliente(respostas) devolve um ClienteFalso com repositório sem tags por padrão."""

    def criar(respostas: dict) -> ClienteFalso:
        return ClienteFalso({(f"/repos/{REPO}/tags", 1): (200, [], None), **respostas})

    return criar


@pytest.fixture
def releases_v1_0_e_v1_1():
    """v1.0 (primeira da história) e v1.1, ambas na janela."""
    return [release("v1.1", "2026-03-15T00:00:00Z"), release("v1.0", "2026-03-01T00:00:00Z")]


# --------------------------------------------------------------------------
# Construtores das respostas da API
# --------------------------------------------------------------------------
def release(tag, publicada_em, draft=False, prerelease=False):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": None if draft else publicada_em,
        "created_at": publicada_em,
    }


def commit(sha, data):
    return {"sha": sha, "commit": {"author": {"date": data}}, "files": ["diff enorme"]}


def compare(*commits, total=None):
    corpo = {"total_commits": len(commits) if total is None else total, "commits": list(commits), "files": ["diff"]}
    return 200, corpo, None


def link_proxima(pagina):
    return f'<https://api.github.com/x?page={pagina}>; rel="next"'


def caminho_releases():
    return f"/repos/{REPO}/releases"


def caminho_tags():
    return f"/repos/{REPO}/tags"


def caminho_compare(base, head):
    return f"/repos/{REPO}/compare/{base}...{head}"
