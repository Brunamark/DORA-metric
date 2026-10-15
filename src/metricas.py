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

CFR (b): release corretiva (RQ 03 b, issue #10)
-----------------------------------------------
Uma release R falha se uma release corretiva que tem R como predecessora for publicada
em até 7 dias depois dela. Releases publicadas nos últimos 7 dias da janela são
censuradas: ainda não se sabe se haverá correção, então ficam fora do denominador.

  Predecessora de uma release: na variante "cronologico" (leitura literal do enunciado),
      a release publicada imediatamente antes; na variante "linha" (padrão), a maior
      versão abaixo dela, com o mesmo prefixo de tag, entre as publicadas antes dela.
      A variante "linha" evita comparar releases de linhas paralelas (25.8.x-lts com
      25.9.x-stable) e de pacotes diferentes de um monorepo (pkg-a@1.2 com pkg-b@0.4).
  Release corretiva: decidida por um critério (CRITERIOS), a partir do tipo de mudança
      de versão em relação à predecessora e dos títulos dos commits entre as duas.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import NamedTuple

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


# --------------------------------------------------------------------------
# Versões de release (CFR b, issue #10)
# --------------------------------------------------------------------------
# prefixo (opcional) + v (opcional) + MAJOR.MINOR[.PATCH[.BUILD]] + sufixo (opcional).
# O prefixo é mínimo (.*?), então "app2-1.2.3" vira prefixo "app2-" e versão 1.2.3.
_RE_VERSAO = re.compile(
    r"^(?P<prefixo>.*?)[vV]?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?:\.(?P<build>\d+))?"
    r"(?P<sufixo>[-+_~.][0-9A-Za-z.\-+_~]*|[A-Za-z][0-9A-Za-z.\-+_~]*)?$"
)
MAJOR_CALENDARIO = 1000   # MAJOR >= 1000 indica versão por calendário (ex.: 2025.10.1)

# Tipos de mudança que contam como "mudou só o patch"
TIPOS_PATCH = frozenset({"patch", "sufixo"})


class Versao(NamedTuple):
    prefixo: str                      # parte da tag antes da versão, em minúsculas ("", "pkg@", "release-")
    numeros: tuple[int, int, int, int]  # MAJOR, MINOR, PATCH, BUILD (ausentes = 0)
    sufixo: str                       # pré-release ou metadado ("-rc1", "+k3s1", "-lts", "b")
    calendario: bool                  # versão por calendário: "patch" não significa correção


def parse_versao(tag: str | None) -> Versao | None:
    """Versão contida no nome da tag, ou None se a tag não seguir MAJOR.MINOR[.PATCH]
    (ex.: "cli-latest", "release-2026-08-21", "v8")."""
    if not tag:
        return None
    m = _RE_VERSAO.match(tag.strip())
    if not m:
        return None
    numeros = tuple(int(m[g] or 0) for g in ("major", "minor", "patch", "build"))
    return Versao(
        prefixo=m["prefixo"].lower(),
        numeros=numeros,
        sufixo=(m["sufixo"] or "").lower(),
        calendario=numeros[0] >= MAJOR_CALENDARIO,
    )


def tipo_mudanca(anterior: Versao | None, atual: Versao | None) -> str | None:
    """"major", "minor", "patch", "sufixo" (só o sufixo mudou, ex.: +k3s1 -> +k3s2),
    "igual", "regressao" (versão menor que a anterior) ou None quando não dá para comparar:
    tag sem versão, prefixos diferentes ou versão por calendário."""
    if anterior is None or atual is None:
        return None
    if anterior.prefixo != atual.prefixo or anterior.calendario or atual.calendario:
        return None
    a, b = anterior.numeros, atual.numeros
    if b < a:
        return "regressao"
    if b[0] != a[0]:
        return "major"
    if b[1] != a[1]:
        return "minor"
    if b[2:] != a[2:]:
        return "patch"
    return "sufixo" if anterior.sufixo != atual.sufixo else "igual"


# --------------------------------------------------------------------------
# Títulos de commit
# --------------------------------------------------------------------------
# v1: exatamente as palavras do enunciado, como palavra inteira ("fix:" e "fix(scope):" casam)
_RE_CORRETIVA = re.compile(r"\b(?:fix|hotfix|revert)\b", re.IGNORECASE)
# ampla: também flexões e variantes ("fixes", "fixed", "bugfix", "hot-fix", "reverted")
_RE_CORRETIVA_AMPLA = re.compile(
    r"\b(?:fix(?:e[sd])?|hot-?fix(?:e[sd])?|bug-?fix(?:e[sd])?|revert(?:s|ed)?)\b", re.IGNORECASE
)
# atualização de dependência (ex.: "fix(deps): update dependency x", "chore(deps): bump y")
_RE_DEPENDENCIA = re.compile(
    r"\b(?:deps?|dependenc(?:y|ies)|bump(?:s|ed)?|dependabot|renovate)\b", re.IGNORECASE
)


def tem_palavra_corretiva(titulo: str | None, ampla: bool = False) -> bool:
    """O título tem fix, hotfix ou revert como palavra inteira (ampla=True aceita flexões)."""
    regex = _RE_CORRETIVA_AMPLA if ampla else _RE_CORRETIVA
    return bool(titulo and regex.search(titulo))


def eh_atualizacao_de_dependencia(titulo: str | None) -> bool:
    return bool(titulo and _RE_DEPENDENCIA.search(titulo))


def eh_merge(titulo: str | None) -> bool:
    return bool(titulo) and titulo.startswith("Merge ")


@dataclass(frozen=True)
class CaracteristicasCommits:
    n_commits: int
    n_merges: int
    n_fix: int          # títulos com fix/hotfix/revert (v1)
    n_fix_amplo: int    # títulos com as variantes amplas, sem contar merges
    n_fix_deps: int     # títulos v1 que são atualização de dependência


def caracteristicas_commits(titulos: Iterable[str]) -> CaracteristicasCommits:
    titulos = [t or "" for t in titulos]
    return CaracteristicasCommits(
        n_commits=len(titulos),
        n_merges=sum(eh_merge(t) for t in titulos),
        n_fix=sum(tem_palavra_corretiva(t) for t in titulos),
        n_fix_amplo=sum(tem_palavra_corretiva(t, ampla=True) for t in titulos if not eh_merge(t)),
        n_fix_deps=sum(tem_palavra_corretiva(t) and eh_atualizacao_de_dependencia(t) for t in titulos),
    )


# --------------------------------------------------------------------------
# Critérios de release corretiva (lógica de três valores: True, False, None = indeterminado)
# --------------------------------------------------------------------------
def _e(*valores):
    if any(v is False for v in valores):
        return False
    return None if any(v is None for v in valores) else True


def _ou(*valores):
    if any(v is True for v in valores):
        return True
    return None if any(v is None for v in valores) else False


def _so_patch(tipo):
    return None if tipo is None else tipo in TIPOS_PATCH


def _tem_fix(c):
    return None if c is None else c.n_fix > 0


def _tem_fix_sem_deps(c):
    return None if c is None else c.n_fix - c.n_fix_deps > 0


def _maioria_fix(c, limiar=0.5):
    if c is None:
        return None
    base = c.n_commits - c.n_merges
    return base > 0 and c.n_fix_amplo / base >= limiar


CRITERIOS = {
    # v1 do enunciado: só o patch mudou E algum commit tem fix/hotfix/revert
    "semver_e_mensagem": lambda t, c: _e(_so_patch(t), _tem_fix(c)),
    "semver_ou_mensagem": lambda t, c: _ou(_so_patch(t), _tem_fix(c)),
    "so_semver": lambda t, c: _so_patch(t),
    "so_mensagem": lambda t, c: _tem_fix(c),
    # refinamentos: ignora commits de dependência; exige que a maioria dos commits seja correção
    "semver_e_mensagem_sem_deps": lambda t, c: _e(_so_patch(t), _tem_fix_sem_deps(c)),
    "semver_e_maioria_fix": lambda t, c: _e(_so_patch(t), _maioria_fix(c)),
}
CRITERIO_PADRAO = "semver_e_mensagem"


def avaliar_criterio(tipo: str | None, carac: CaracteristicasCommits | None, criterio: str = CRITERIO_PADRAO):
    """Aplica um critério a uma release já descrita (tipo de mudança e commits).
    `carac=None` significa commits desconhecidos (ex.: compare com 404)."""
    if criterio not in CRITERIOS:
        raise ValueError(f"critério desconhecido: {criterio} (opções: {', '.join(CRITERIOS)})")
    return CRITERIOS[criterio](tipo, carac)


def eh_corretiva(release: str, anterior: str | None, mensagens: Iterable[str] | None,
                 criterio: str = CRITERIO_PADRAO) -> bool | None:
    """A release (tag) é corretiva em relação à anterior (tag), dados os títulos dos commits
    entre as duas? None = indeterminado (ex.: tag sem versão num critério que exige versão).
    Sem anterior (primeira release da linha), não há o que corrigir: False."""
    if anterior is None:
        return False
    tipo = tipo_mudanca(parse_versao(anterior), parse_versao(release))
    carac = None if mensagens is None else caracteristicas_commits(mensagens)
    return avaliar_criterio(tipo, carac, criterio)


# --------------------------------------------------------------------------
# Predecessora de cada release
# --------------------------------------------------------------------------
PAREAMENTOS = ("linha", "cronologico")
PAREAMENTO_PADRAO = "linha"


@dataclass(frozen=True)
class ReleasePublicada:
    tag: str
    publicada_em: datetime


def predecessoras(releases: Sequence[ReleasePublicada], pareamento: str = PAREAMENTO_PADRAO) -> dict[str, str | None]:
    """tag -> tag da predecessora (None = primeira da linha/história).
    cronologico: a publicada imediatamente antes.
    linha: a maior versão menor ou igual, com o mesmo prefixo, entre as publicadas antes
           (empate na versão, ex.: +k3s1 e +k3s2, fica com a mais recente). Tag sem versão
           usa a predecessora cronológica.
    Releases publicadas no mesmo instante mantêm a ordem recebida (a mesma do lead time)."""
    if pareamento not in PAREAMENTOS:
        raise ValueError(f"pareamento desconhecido: {pareamento} (opções: {', '.join(PAREAMENTOS)})")
    ordem = sorted(releases, key=lambda r: r.publicada_em)
    resultado = {}
    vistas_por_prefixo = defaultdict(list)   # prefixo -> [(numeros, publicada_em, tag)] já publicadas
    for i, r in enumerate(ordem):
        anterior_cronologica = ordem[i - 1].tag if i else None
        v = parse_versao(r.tag)
        if pareamento == "cronologico" or v is None:
            resultado[r.tag] = anterior_cronologica
        else:
            candidatas = [c for c in vistas_por_prefixo[v.prefixo] if c[0] <= v.numeros]
            resultado[r.tag] = max(candidatas)[2] if candidatas else None
        if v is not None:
            vistas_por_prefixo[v.prefixo].append((v.numeros, r.publicada_em, r.tag))
    return resultado


# --------------------------------------------------------------------------
# CFR (b)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ReleaseClassificada:
    tag: str
    publicada_em: datetime
    predecessora: str | None
    corretiva: bool | None       # resultado do critério (None = indeterminado, conta como não)


class ResultadoCFR(NamedTuple):
    cfr: float | None
    n_avaliadas: int
    n_falhas: int
    n_censuradas: int


def situacao_releases(releases: Sequence[ReleaseClassificada], fim_janela: datetime, prazo_dias: int = 7,
                      inicio_janela: datetime | None = None) -> dict[str, str]:
    """tag -> "falhou", "nao_falhou" ou "censurada", para cada release dentro da janela.
    R falhou se alguma release corretiva que tem R como predecessora foi publicada em até
    `prazo_dias` depois de R (o 7º dia conta; o 8º, não). R publicada nos últimos
    `prazo_dias` da janela é censurada."""
    prazo = timedelta(days=prazo_dias)
    corrigidas = defaultdict(list)  # tag da predecessora -> datas das corretivas que a corrigem
    for s in releases:
        if s.corretiva is True and s.predecessora is not None:
            corrigidas[s.predecessora].append(s.publicada_em)

    situacao = {}
    for r in releases:
        if r.publicada_em > fim_janela or (inicio_janela and r.publicada_em < inicio_janela):
            continue
        if r.publicada_em > fim_janela - prazo:
            situacao[r.tag] = "censurada"
        elif any(timedelta(0) <= d - r.publicada_em <= prazo for d in corrigidas[r.tag]):
            situacao[r.tag] = "falhou"
        else:
            situacao[r.tag] = "nao_falhou"
    return situacao


def cfr_entrega(releases: Sequence[ReleaseClassificada], fim_janela: datetime, prazo_dias: int = 7,
                inicio_janela: datetime | None = None) -> ResultadoCFR:
    """CFR (b) = releases que falharam / releases avaliadas (as censuradas ficam fora).
    Retorna (cfr, n_avaliadas, n_falhas, n_censuradas); cfr é None sem releases avaliadas."""
    situacao = situacao_releases(releases, fim_janela, prazo_dias, inicio_janela).values()
    falhas = sum(s == "falhou" for s in situacao)
    censuradas = sum(s == "censurada" for s in situacao)
    avaliadas = len(situacao) - censuradas
    return ResultadoCFR(falhas / avaliadas if avaliadas else None, avaliadas, falhas, censuradas)
