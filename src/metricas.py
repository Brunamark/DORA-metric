"""
Lab03S01 - Card B: métricas de lead time (RQ 02).

Cada release publicada (draft = false, prerelease = false) é tratada como um deploy.
O lead time mede o tempo entre um commit e a release que o entregou, usando a data de
autoria do commit (commit.author.date).

Duas variantes:
  (a) por release: data da release - data do commit mais antigo que ela entregou;
      o valor do repositório é a mediana entre as releases.
  (b) por commit: data da release - data de cada commit entregue;
      o valor do repositório é a mediana entre todos os commits.

Todas as durações são em dias (float).
"""

from datetime import datetime
from statistics import median

SEGUNDOS_POR_DIA = 86400


def _dias(inicio: datetime, fim: datetime) -> float:
    return (fim - inicio).total_seconds() / SEGUNDOS_POR_DIA


def lead_time_release(data_release: datetime, datas_commits: list[datetime]) -> float | None:
    """Variante (a): dias entre o commit mais antigo e a release.
    Retorna None se a release não entregou nenhum commit novo."""
    if not datas_commits:
        return None
    return _dias(min(datas_commits), data_release)


def lead_time_commit(data_release: datetime, datas_commits: list[datetime]) -> list[float]:
    """Variante (b): dias entre cada commit e a release, na ordem recebida."""
    return [_dias(data, data_release) for data in datas_commits]


def mediana_lead_time_release(releases: list[tuple[datetime, list[datetime]]]) -> float | None:
    """Valor do repositório na variante (a): mediana dos lead times por release.
    `releases` = [(data_release, [datas dos commits]), ...]. Releases sem commits são ignoradas."""
    valores = [lt for data, commits in releases if (lt := lead_time_release(data, commits)) is not None]
    return median(valores) if valores else None


def mediana_lead_time_commit(releases: list[tuple[datetime, list[datetime]]]) -> float | None:
    """Valor do repositório na variante (b): mediana dos lead times de todos os commits."""
    valores = [lt for data, commits in releases for lt in lead_time_commit(data, commits)]
    return median(valores) if valores else None
