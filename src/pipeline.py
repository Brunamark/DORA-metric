#!/usr/bin/env python3
"""
Lab03 - pipeline completo de coleta, com um único comando.

Etapas, nesta ordem (todas usam a mesma janela e o mesmo cache):
  selecao   seleção de repositórios, funil e metadados        (selecao_repos.py, Card A)
  releases  releases, tags, commits entre releases, lead time (coleta_releases.py, Card B)
  runs      workflow runs, CFR (a) e tempo de recuperação     (coleta_runs.py, Card C)
  corretivas releases corretivas e CFR (b)                    (corretivas.py, issue #10)
            -> fora do padrão: só roda com --etapas corretivas (rotulagem cega da amostra-ouro)

Uso, a partir da raiz do repositório:
    export GITHUB_TOKEN=ghp_xxx                 # PowerShell: $env:GITHUB_TOKEN="ghp_xxx"
    python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01

Interrompeu (Ctrl+C, rate limit, rede)? Rode o mesmo comando: as respostas já obtidas
estão no cache e a coleta continua de onde parou.
"""

import argparse
import sys
import time
from pathlib import Path

import coleta_releases
import coleta_runs
import corretivas
import selecao_repos
from selecao_repos import (
    CACHE_PADRAO,
    DADOS_PADRAO,
    FAIXAS_PADRAO,
    ErroDeToken,
    GitHubClient,
    ler_repos,
    ler_token,
    parse_janela,
)

ETAPAS = ("selecao", "releases", "runs", "corretivas")
# "corretivas" fica fora do padrão até a amostra-ouro ser rotulada (issue #10): quem rotula
# não pode ver a saída da heurística antes de commitar os próprios rótulos.
ETAPAS_PADRAO = ("selecao", "releases", "runs")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Lab03 - pipeline de coleta das métricas DORA")
    ap.add_argument("--inicio", required=True, help="início da janela (AAAA-MM-DD)")
    ap.add_argument("--fim", required=True, help="fim da janela (AAAA-MM-DD)")
    ap.add_argument("--etapas", nargs="+", choices=ETAPAS, default=list(ETAPAS_PADRAO),
                    help="etapas a executar, sempre na ordem do pipeline "
                         "(padrão: selecao releases runs; corretivas só quando pedida)")
    ap.add_argument("--alvo", type=int, default=100, help="nº de repositórios da amostra")
    ap.add_argument("--min-releases", type=int, default=5)
    ap.add_argument("--min-runs", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--faixas", nargs="+", default=FAIXAS_PADRAO, help="faixas de estrelas da busca")
    ap.add_argument("--saida", default=str(DADOS_PADRAO), help="pasta dos CSVs de saída")
    ap.add_argument("--cache", default=str(CACHE_PADRAO), help="pasta do cache de respostas")
    args = ap.parse_args(argv)

    ini, fim = parse_janela(args.inicio, args.fim)
    saida = Path(args.saida)
    client = GitHubClient(ler_token(), args.cache)
    etapas = [e for e in ETAPAS if e in args.etapas]   # sempre na ordem do pipeline
    print(f"Janela: {ini:%Y-%m-%d} a {fim:%Y-%m-%d} | etapas: {' -> '.join(etapas)} | saída: {saida}\n")

    try:
        for etapa in etapas:
            comeco = time.monotonic()
            print(f"===== Etapa: {etapa} =====", flush=True)
            if etapa == "selecao":
                selecao_repos.executar(client, ini, fim, saida, args.alvo, args.min_releases,
                                       args.min_runs, args.seed, args.faixas)
            else:
                repos = ler_repos(saida / "repos_selecionados.csv")
                if etapa == "releases":
                    coleta_releases.executar(client, ini, fim, repos, saida)
                elif etapa == "runs":
                    coleta_runs.executar(client, ini, fim, repos, saida)
                else:
                    corretivas.executar(client, ini, fim, repos, saida)
            print(f"===== {etapa} concluída em {time.monotonic() - comeco:.0f}s =====\n", flush=True)
    except ErroDeToken as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        sys.exit("\nInterrompido. As respostas já feitas estão no cache: rode o mesmo comando para retomar.")

    print(f"Pipeline concluído. Chamadas à API: {client.chamadas} | respostas do cache: {client.cache_hits}")


if __name__ == "__main__":
    main()
