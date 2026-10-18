# Rascunho — Metodologia: Coleta

Texto para a subseção do artigo (template SBC), issue #8. Revisar e passar para o Overleaf. Os números entre colchetes saem dos CSVs de `src/data/` e do log da execução do pipeline com a amostra final.

---

**Coleta.** A coleta é feita por um pipeline em Python, executado com um único comando (`python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01`). As etapas são, em ordem: seleção, releases, variantes, *workflow runs* e consolidação. Todas usam a mesma janela de observação, de 1º de outubro de 2025 a 1º de outubro de 2026 (UTC), e consideram só o *default branch* de cada repositório. O token de acesso é lido de uma variável de ambiente e nunca é versionado.

*Releases e commits.* As releases vêm de `/repos/{owner}/{repo}/releases`, com 100 itens por página, seguindo o cabeçalho `Link` (`rel="next"`). A paginação para quando alcança releases publicadas 90 dias antes do início da janela, o que garante a release anterior à primeira release da janela. Os commits entregues por uma release R vêm de `/compare/{anterior}...{R}`. Sem paginação, esse *endpoint* devolve no máximo 250 commits. Por isso, seguimos as páginas de 100 commits até o fim e conferimos o total com o campo `total_commits` da resposta ([N] releases ficaram com a lista incompleta). Comparações que retornaram HTTP 404, por tag apagada ou reescrita, foram ignoradas no lead time e contadas: [N] releases na definição principal e [N] na variante com pré-releases. As tags vêm de `/repos/{owner}/{repo}/tags`. Como a API REST não informa a data de uma tag, usamos a data do commit para o qual ela aponta (`committedDate`), consultada pela API GraphQL em lotes de 100 commits por requisição. Foram [N] tags, das quais [N] ficaram sem data porque o commit apontado não existe mais.

*Workflow runs.* Os runs vêm de `/actions/runs`, filtrados por *branch*, `event=push` e intervalo de criação (`created`). Com filtros, a API devolve no máximo 1.000 resultados por consulta, mesmo com paginação. Por isso, a janela é consultada mês a mês. Um mês cujo `total_count` chega a 1.000 é dividido ao meio, por dias e, dentro de um dia, por horário, até cada parte caber no teto. Foram [N] consultas, das quais [N] precisaram ser divididas; nenhuma parte ficou no teto [ou: N partes ficaram no teto, nos repositórios X e Y, e os runs desses intervalos estão incompletos]. Ao todo foram coletados [N] runs.

*Cache, retomada e limites da API.* Toda resposta da API é gravada em disco, um arquivo JSON por URL e parâmetros. Das respostas grandes (`/compare` e `/actions/runs`), guardamos só os campos usados. Se a coleta for interrompida (por *rate limit*, falha de rede ou interrupção manual), executar o mesmo comando retoma do ponto em que parou, sem repetir chamadas. A consolidação final não faz nenhuma chamada. O pipeline lê os cabeçalhos `X-RateLimit-Remaining` e `X-RateLimit-Reset` e pausa sozinho quando a cota de 5.000 requisições por hora se esgota. Erros 5xx e falhas de rede são repetidos com *backoff* exponencial (1, 2, 4, 8 e 16 s, até cinco tentativas). Respostas HTTP 401 interrompem a coleta e nunca vão para o cache.

*Volume.* A coleta da amostra final fez [N] requisições REST e [N] GraphQL e levou [N] horas numa única máquina. Coletamos [N] releases na janela, [N] commits entregues e [N] *workflow runs*. Um repositório com erro de API não é descartado em silêncio: ele permanece no dataset com o erro registrado nas colunas de status ([N] casos).

*Dataset.* Os resumos por repositório de cada etapa são consolidados num único arquivo (`dataset.csv`), com uma linha por repositório e todas as variantes das métricas. Cada coluna de cada CSV está documentada no dicionário de dados do repositório, com tipo, unidade e fórmula ou origem na API.

*Ameaças ligadas à coleta* (para a seção de ameaças à validade):
- **Repositórios em movimento.** Os repositórios continuam mudando depois da janela, então releases e tags podem ser apagadas ou reescritas antes da coleta; esses casos aparecem como 404.
- **Data da tag.** A data de uma tag é a do commit apontado, e não a da criação da tag, o que antecipa a data de tags criadas depois do commit.
- **Pareamento por data.** As pré-releases ordenadas por data de publicação podem misturar linhas de versão diferentes na variante C2.
