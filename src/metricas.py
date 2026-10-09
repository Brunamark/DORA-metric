"""
Lab03S01 - métricas DORA calculadas a partir dos dados coletados.

Lead time (RQ 02, Card B)
-------------------------
Cada release publicada (draft = false, prerelease = false) é tratada como um deploy.
O lead time mede o tempo entre um commit e a release que o entregou, usando a data de
autoria do commit (commit.author.date).

Duas variantes:
  (a) por release: data da release - data do commit mais antigo que ela entregou;
      o valor do repositório é a mediana entre as releases.
  (b) por commit: data da release - data de cada commit entregue;
      o valor do repositório é a mediana entre todos os commits.

Durações do lead time em dias (float).

CFR (a) e tempo de recuperação (RQ 03 e RQ 04, Card C)
------------------------------------------------------
Workflow runs do default branch com event = push. O campo conclusion classifica o run:
success é sucesso; failure, timed_out e startup_failure são falha; os demais valores
(cancelled, skipped, neutral, action_required, stale, vazio) são ignorados em tudo.

  CFR (a): falhas / (falhas + sucessos), com todos os workflows juntos (proporção 0..1).
  Episódio de falha: dentro de um mesmo workflow, começa na primeira falha após um
      sucesso (run_started_at) e termina no próximo sucesso (updated_at). Episódio sem
      sucesso até o fim da janela é censurado: fica fora da mediana, mas é contado.
  Tempo de recuperação: mediana das durações de todos os episódios fechados de todos
      os workflows, em horas (float).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from statistics import median

SEGUNDOS_POR_DIA = 86400
SEGUNDOS_POR_HORA = 3600

CONCLUSOES_SUCESSO = frozenset({"success"})
CONCLUSOES_FALHA = frozenset({"failure", "timed_out", "startup_failure"})


def _dias(inicio: datetime, fim: datetime) -> float:
    return (fim - inicio).total_seconds() / SEGUNDOS_POR_DIA


def _horas(inicio: datetime, fim: datetime) -> float:
    return (fim - inicio).total_seconds() / SEGUNDOS_POR_HORA


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


# --------------------------------------------------------------------------
# CFR (a) e tempo de recuperação (RQ 03 e RQ 04)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Run:
    """Workflow run, só com os campos usados nas métricas."""

    id: int
    workflow_id: int
    conclusao: str | None
    criado_em: datetime                # created_at: ordena os runs (não muda em re-runs)
    iniciado_em: datetime | None       # run_started_at: início do episódio
    atualizado_em: datetime            # updated_at: fim do run que encerra o episódio


@dataclass(frozen=True)
class Episodio:
    workflow_id: int
    inicio: datetime                   # run_started_at da primeira falha após um sucesso
    fim: datetime | None               # updated_at do próximo sucesso; None = censurado
    n_falhas: int
    run_inicio: int
    run_fim: int | None

    @property
    def censurado(self) -> bool:
        return self.fim is None

    @property
    def duracao_horas(self) -> float | None:
        return None if self.fim is None else _horas(self.inicio, self.fim)


def classificar_conclusao(conclusao: str | None) -> str | None:
    """'sucesso', 'falha' ou None (run ignorado em todos os cálculos)."""
    if conclusao in CONCLUSOES_SUCESSO:
        return "sucesso"
    if conclusao in CONCLUSOES_FALHA:
        return "falha"
    return None


def cfr_runs(runs: Iterable[Run]) -> float | None:
    """CFR (a): falhas / (falhas + sucessos). None se não houver runs válidos."""
    classes = [c for r in runs if (c := classificar_conclusao(r.conclusao))]
    if not classes:
        return None
    return classes.count("falha") / len(classes)


def _episodios_do_workflow(runs: list[Run]) -> tuple[list[Episodio], bool]:
    """Episódios de um único workflow. O bool indica falhas antes do primeiro sucesso
    da janela: elas não abrem episódio, porque o início real ficou fora da janela."""
    episodios = []
    visto_sucesso = False
    falha_sem_sucesso_anterior = False
    primeira_falha, n_falhas = None, 0

    for run in sorted(runs, key=lambda r: (r.criado_em, r.id)):
        classe = classificar_conclusao(run.conclusao)
        if classe == "falha":
            if primeira_falha is not None:
                n_falhas += 1
            elif visto_sucesso:
                primeira_falha, n_falhas = run, 1
            else:
                falha_sem_sucesso_anterior = True
        elif classe == "sucesso":
            if primeira_falha is not None:
                episodios.append(_episodio(primeira_falha, n_falhas, run))
                primeira_falha = None
            visto_sucesso = True

    if primeira_falha is not None:
        episodios.append(_episodio(primeira_falha, n_falhas, None))
    return episodios, falha_sem_sucesso_anterior


def _episodio(primeira_falha: Run, n_falhas: int, sucesso: Run | None) -> Episodio:
    return Episodio(
        workflow_id=primeira_falha.workflow_id,
        inicio=primeira_falha.iniciado_em or primeira_falha.criado_em,
        fim=sucesso.atualizado_em if sucesso else None,
        n_falhas=n_falhas,
        run_inicio=primeira_falha.id,
        run_fim=sucesso.id if sucesso else None,
    )


def episodios_falha(runs: Iterable[Run]) -> tuple[list[Episodio], int]:
    """Episódios de falha de todos os workflows, formados dentro de cada workflow.
    Retorna (episódios, nº de workflows com falhas antes do primeiro sucesso da janela)."""
    por_workflow: dict[int, list[Run]] = defaultdict(list)
    for run in runs:
        por_workflow[run.workflow_id].append(run)

    episodios, sem_sucesso_anterior = [], 0
    for workflow_id in sorted(por_workflow):
        eps, sem_sucesso = _episodios_do_workflow(por_workflow[workflow_id])
        episodios.extend(eps)
        sem_sucesso_anterior += sem_sucesso
    return episodios, sem_sucesso_anterior


def tempo_recuperacao(episodios: Iterable[Episodio]) -> float | None:
    """Valor do repositório: mediana, em horas, dos episódios fechados (censurados ficam fora)."""
    duracoes = [e.duracao_horas for e in episodios if not e.censurado]
    return median(duracoes) if duracoes else None


def proporcao_censurados(episodios: Iterable[Episodio]) -> float | None:
    """Censurados / total de episódios. None se não houver episódios."""
    episodios = list(episodios)
    if not episodios:
        return None
    return sum(e.censurado for e in episodios) / len(episodios)
