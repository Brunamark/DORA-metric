# Lab03 · Mineração de métricas DORA

Pipeline de coleta para o Lab03. Um único comando executa as três etapas da Sprint 1:

| Etapa | Script | Card / issue | O que faz |
|---|---|---|---|
| `selecao` | `src/selecao_repos.py` | A, #1 | Seleção de repositórios, funil de seleção e metadados |
| `releases` | `src/coleta_releases.py` | B, #2 | Releases, tags, commits entre releases e lead time |
| `runs` | `src/coleta_runs.py` | C, #3 | Workflow runs (divididos por mês), CFR (a) e tempo de recuperação |
| `corretivas` | `src/corretivas.py` | #10 (Sprint 2) | Releases corretivas e CFR (b). **Fora do comando padrão** até a amostra-ouro ser rotulada (ver abaixo) |

As etapas usam a mesma janela, o mesmo cache e gravam os CSVs em `src/data/`.

## Requisitos

- Python 3.10+
- Dependências: `requests` (coleta), `pytest` e `pytest-cov` (testes)
- Token do GitHub (Personal Access Token). Para repositórios públicos, não precisa de nenhum escopo.

## Instalação

```bash
git clone <url-do-repositorio-do-grupo>
cd <pasta-do-repositorio>

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Token do GitHub

O token é lido da variável de ambiente `GITHUB_TOKEN`. **Nunca commite o token.**

```bash
export GITHUB_TOKEN=ghp_seu_token      # Linux/macOS
set GITHUB_TOKEN=ghp_seu_token         # Windows (cmd)
$env:GITHUB_TOKEN="ghp_seu_token"      # Windows (PowerShell)
```

## Como rodar

**Comando único**, a partir da raiz do repositório, com a janela de observação (12 meses) definida pelo professor:

```bash
python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01
```

O comando roda `selecao` → `releases` → `runs`. Para rodar só parte do pipeline (por exemplo, quando a seleção já está pronta), use `--etapas`:

```bash
python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01 --etapas releases runs
```

Teste rápido antes da coleta completa (grava numa pasta separada para não sobrescrever os CSVs da amostra):

```bash
python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01 --alvo 5 --saida teste_rapido
```

Cada etapa também pode ser executada sozinha (`python src/selecao_repos.py ...`, `python src/coleta_releases.py ...`, `python src/coleta_runs.py ...`), com os mesmos parâmetros de janela. Os caminhos padrão são relativos a `src/`, então o resultado é o mesmo de qualquer pasta de onde o comando for executado.

**Tempo e cota.** A seleção já está no cache versionado e roda em segundos, sem chamadas à API. As etapas `releases` e `runs` fazem milhares de chamadas e devem atingir o rate limit (5.000 requisições por hora) algumas vezes. O script espera sozinho; se precisar parar, use `Ctrl+C` e rode o mesmo comando depois.

### Parâmetros

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--inicio` | (obrigatório) | Início da janela, `AAAA-MM-DD` |
| `--fim` | (obrigatório) | Fim da janela, `AAAA-MM-DD` |
| `--etapas` | `selecao releases runs` | Etapas a executar (sempre na ordem do pipeline). `corretivas` só roda quando pedida |
| `--alvo` | `100` | Nº de repositórios da amostra |
| `--min-releases` | `5` | Mínimo de releases publicadas na janela |
| `--min-runs` | `50` | Mínimo de workflow runs válidos (push, default branch) |
| `--seed` | `42` | Seed do embaralhamento (reprodutibilidade) |
| `--faixas` | 6 faixas de 1.000 a >60.000 estrelas | Faixas de estrelas da busca (`1000..2000`, `>60000`…) |
| `--saida` | `src/data` | Pasta dos CSVs de saída |
| `--cache` | `src/.cache/github` | Pasta do cache de respostas da API |

## Seleção de repositórios (Card A, issue #1)

- Busca candidatos fatiando por faixas de estrelas (a busca retorna no máximo 1.000 resultados por consulta).
- Embaralha os candidatos com seed fixa e avalia um a um até atingir o alvo.
- Aplica os filtros, nesta ordem:
  - usa GitHub Actions;
  - tem ≥ 5 releases publicadas na janela (`draft = false`, `prerelease = false`);
  - tem ≥ 50 workflow runs válidos no default branch, com `event = push` e `conclusion` em `success`, `failure`, `timed_out` ou `startup_failure`.
- Coleta estrelas, linguagem, contribuidores, idade e `default_branch`.

### Saídas (pasta `src/data/`)

| Arquivo | Conteúdo |
|---|---|
| `repos_selecionados.csv` | Amostra final com os metadados |
| `descartados.csv` | Repositórios descartados e o motivo |
| `funil.csv` / `funil.md` | Funil de seleção (vai para a Metodologia do artigo) |

#### Colunas de `repos_selecionados.csv`

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `url` | texto | `html_url` do repositório |
| `stars` | inteiro | `stargazers_count` |
| `language` | texto | linguagem principal (`language`) |
| `contributors` | inteiro | nº de contribuidores (última página de `/contributors?per_page=1&anon=true`) |
| `created_at` | data/hora ISO | criação do repositório |
| `age_days` | inteiro | **dias**, de `created_at` até o fim da janela |
| `default_branch` | texto | branch principal |
| `releases_in_window` | inteiro | releases publicadas dentro da janela |
| `valid_runs_in_window` | inteiro | runs válidos dentro da janela |

## Cache e retomada

- Toda resposta da API é salva em `src/.cache/github/` (um JSON por URL + parâmetros). Das respostas grandes (`/compare` e `/actions/runs`), só os campos usados vão para o cache. Quando o formato salvo muda, a chave do cache ganha uma versão (ex.: `compare-v2-mensagem`, que inclui a mensagem dos commits) e as respostas no formato antigo deixam de ser usadas.
- Se o script for interrompido (`Ctrl+C`, queda de rede, rate limit), **rode o mesmo comando de novo**: ele continua de onde parou, sem repetir chamadas.
- As respostas da seleção estão versionadas, para que a seleção seja reproduzida exatamente. Respostas novas ficam só na máquina local (ver `.gitignore`).
- Cada resposta é gravada num arquivo temporário e renomeada no fim, então uma interrupção no meio da gravação não deixa JSON corrompido. Um arquivo ilegível é tratado como ausente e consultado de novo.
- Para refazer a coleta do zero, apague a pasta `src/.cache/`.

## Rate limit e erros

- O script lê `X-RateLimit-Remaining` e `X-RateLimit-Reset` e **espera sozinho** quando a cota acaba. A busca tem cota própria, menor, então pausas nessa etapa são normais.
- Erros 5xx e falhas de rede são repetidos com backoff exponencial (1, 2, 4, 8, 16 s).

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Defina a variável de ambiente GITHUB_TOKEN` | Token não exportado | Exporte o token no terminal atual |
| HTTP 401 / `Bad credentials` | Token inválido ou expirado | Gere um novo token e rode o mesmo comando. A coleta para no primeiro 401 e essa resposta nunca vai para o cache |
| `só N aprovados de 100` | Poucos candidatos passaram nos filtros | Amplie as faixas com `--faixas` |
| Aviso de faixa com mais de 1.000 resultados | A faixa de estrelas é larga demais | Divida a faixa em intervalos menores |
| Execução lenta | Rate limit da busca ou da API | Deixe rodando; o cache preserva o progresso |

## Releases, commits entre releases e lead time (Card B, issue #2)

Etapa `releases` do pipeline. Sozinha: `python src/coleta_releases.py --inicio 2025-10-01 --fim 2026-10-01`.

- Deploy = release publicada (`draft = false`, `prerelease = false`). A primeira release do histórico não tem anterior e é ignorada.
- Para cada release da janela, os commits entregues vêm de `/compare/{anterior}...{release}`, seguindo a paginação até o fim. Tag inexistente ou reescrita (HTTP 404) pula a release e entra na contagem `releases_404`.
- O lead time usa a data de autoria do commit (`commit.author.date`), em **dias**:
  - variante (a), `lead_time_release()`: release − commit mais antigo; o valor do repositório é a mediana entre as releases;
  - variante (b), `lead_time_commit()`: release − cada commit; o valor do repositório é a mediana de todos os commits.

| Arquivo | Conteúdo |
|---|---|
| `releases.csv` | Todas as releases listadas, com `status` (`ok`, `sem_commits`, `tag_404`, `primeira_release`, `fora_da_janela`, `excluida_draft`, `excluida_prerelease`) |
| `commits_releases.csv` | Commits entregues por release e o lead time de cada um. **Não é versionado** (passa de 250 MB com a amostra de 100 repositórios): é regerado pelo pipeline |
| `tags.csv` | Tags de cada repositório (variante da RQ 07) |
| `lead_time_repos.csv` | Resumo por repositório, com as medianas das duas variantes |

### Dicionário de dados

`releases.csv`: uma linha por release listada.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `tag_name` | texto | `tag_name` da release |
| `draft` / `prerelease` | booleano | campos `draft` e `prerelease` da release |
| `published_at` | data/hora ISO | `published_at` da release (vazio em drafts) |
| `na_janela` | booleano | release publicada com `published_at` dentro da janela |
| `tag_anterior` | texto | tag da release publicada imediatamente anterior (base do `compare`) |
| `status` | texto | resultado no cálculo de lead time (valores na tabela acima) |
| `n_commits` | inteiro | commits entregues pela release (`compare/{tag_anterior}...{tag_name}`) |
| `total_commits_api` | inteiro | `total_commits` informado pelo `compare`; diferente de `n_commits` indica comparação incompleta |
| `lead_time_release_dias` | decimal | **dias**, `published_at − min(commit.author.date)`, variante (a) |

`commits_releases.csv`: uma linha por commit entregue em release com `status = ok`.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `tag_name` | texto | release que entregou o commit |
| `sha` | texto | `sha` do commit |
| `author_date` | data/hora ISO | `commit.author.date` |
| `lead_time_dias` | decimal | **dias**, `published_at − commit.author.date`, variante (b) |
| `mensagem` | texto | primeira linha de `commit.message` (até 300 caracteres), usada pela heurística de release corretiva (CFR b) |

`tags.csv`: uma linha por tag (variante da RQ 07).

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `tag_name` | texto | `name` da tag |
| `sha` | texto | `commit.sha` apontado pela tag (a data da tag é a data desse commit) |

`lead_time_repos.csv`: uma linha por repositório.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `status_releases` | texto | `ok` ou `erro_http_<código>` ao listar as releases (o repositório fica sem métricas, mas não some do CSV) |
| `status_tags` | texto | `ok` ou `erro_http_<código>` ao listar as tags |
| `releases_na_janela` | inteiro | releases publicadas (sem draft e sem prerelease) dentro da janela |
| `releases_calculadas` | inteiro | releases da janela com lead time calculado (`status = ok`) |
| `releases_sem_commits` | inteiro | releases da janela sem commits novos |
| `releases_404` | inteiro | releases puladas porque o `compare` retornou 404 |
| `releases_erro` | inteiro | releases puladas por outro erro HTTP no `compare` |
| `releases_commits_incompletos` | inteiro | releases em que `n_commits` ≠ `total_commits_api` |
| `commits` | inteiro | commits entregues pelas releases calculadas |
| `commits_lead_time_negativo` | inteiro | commits com `commit.author.date` posterior à release (dado inconsistente, mantido no cálculo) |
| `lead_time_release_mediana_dias` | decimal | **dias**, mediana de `lead_time_release_dias`, variante (a) |
| `lead_time_commit_mediana_dias` | decimal | **dias**, mediana de `lead_time_dias` de todos os commits, variante (b) |

## Workflow runs, CFR (a) e tempo de recuperação (Card C, issue #3)

Etapa `runs` do pipeline. Sozinha: `python src/coleta_runs.py --inicio 2025-10-01 --fim 2026-10-01`.

- Runs considerados: default branch do repositório (`default_branch` de `repos_selecionados.csv`), `event = push`, `created_at` dentro da janela.
- **Divisão mensal.** A janela é dividida em meses do calendário e cada mês é uma consulta `/actions/runs?branch=…&event=push&created=AAAA-MM-DD..AAAA-MM-DD`, com paginação até o fim. Com filtros, a API devolve no máximo **1.000 runs por consulta**: se o `total_count` de um mês chega a 1.000, o mês é dividido ao meio (por dias e, dentro de um dia, por horário) até cada pedaço caber. Um pedaço que não dá para dividir mais (menos de 1 hora) e continua no teto é marcado como incompleto (`no_teto` em `runs_fatias.csv`, `fatias_no_teto` no resumo). Todas as consultas ficam registradas em `runs_fatias.csv`, para conferir que nenhum mês ficou no teto.
- **Classificação** pelo campo `conclusion`: `success` é sucesso; `failure`, `timed_out` e `startup_failure` são falha; os demais (`cancelled`, `skipped`, `neutral`, `action_required`, `stale`, vazio) são ignorados em todos os cálculos.
- **CFR (a)** = falhas ÷ (falhas + sucessos), todos os workflows juntos.
- **Tempo de recuperação.** Dentro de cada workflow, um episódio começa na primeira falha após um sucesso (`run_started_at`; se vier vazio, `created_at`) e termina no próximo sucesso do mesmo workflow (`updated_at`). O valor do repositório é a mediana dos episódios fechados de todos os workflows. Episódio sem sucesso até o fim da janela é **censurado**: não entra na mediana, mas é contado (`episodios_censurados`, `proporcao_censurados`). Falhas antes do primeiro sucesso da janela não abrem episódio, porque o início real ficou fora dela (`workflows_falha_sem_sucesso_anterior`).

| Arquivo | Conteúdo |
|---|---|
| `runs.csv` | Um run por linha, com a classificação |
| `episodios.csv` | Episódios de falha, fechados e censurados |
| `runs_fatias.csv` | Cada consulta feita à API (mês ou pedaço), com o `total_count` |
| `workflow_runs_repos.csv` | Resumo por repositório: CFR (a), recuperação e censura |

### Dicionário de dados

`runs.csv`: uma linha por workflow run coletado.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `run_id` | inteiro | `id` do run |
| `workflow_id` | inteiro | `workflow_id` do run (agrupa os episódios) |
| `workflow_name` | texto | `name` do run |
| `conclusion` | texto | `conclusion` do run (vazio = em andamento) |
| `classe` | texto | `sucesso`, `falha` ou `ignorado`, pela tabela de `conclusion` |
| `created_at` | data/hora ISO | `created_at`: ordena os runs e define se o run está na janela |
| `run_started_at` | data/hora ISO | `run_started_at`: início de um episódio |
| `updated_at` | data/hora ISO | `updated_at`: fim do run que encerra um episódio |
| `run_attempt` | inteiro | `run_attempt` (re-runs mantêm o mesmo `run_id`) |

`episodios.csv`: uma linha por episódio de falha.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `workflow_id` | inteiro | workflow em que o episódio ocorreu |
| `run_inicio` / `run_fim` | inteiro | `run_id` da primeira falha / do sucesso que encerrou o episódio (vazio se censurado) |
| `inicio` | data/hora ISO | `run_started_at` da primeira falha |
| `fim` | data/hora ISO | `updated_at` do sucesso (vazio se censurado) |
| `n_falhas` | inteiro | runs com falha dentro do episódio |
| `censurado` | booleano | `True` se não houve sucesso até o fim da janela |
| `duracao_horas` | decimal | **horas**, `fim − inicio` (vazio se censurado) |

`runs_fatias.csv`: uma linha por consulta à API.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `inicio` / `fim` | data/hora ISO | limites do filtro `created` da consulta |
| `total_count` | inteiro | `total_count` informado pela API |
| `dividida` | booleano | a fatia atingiu 1.000 e foi dividida em duas |
| `no_teto` | booleano | a fatia atingiu 1.000 e não pôde ser dividida: contagem incompleta |
| `status` | texto | `ok` ou `erro_http_<código>` |

`workflow_runs_repos.csv`: uma linha por repositório.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `default_branch` | texto | branch consultado |
| `status_runs` | texto | `ok` ou `erro_http_<código>` (o repositório fica sem métricas, mas não some do CSV) |
| `fatias_consultadas` | inteiro | consultas feitas (13 meses-calendário + divisões) |
| `fatias_divididas` | inteiro | consultas que atingiram 1.000 e foram divididas |
| `fatias_no_teto` | inteiro | consultas que ficaram no teto (≠ 0 indica contagem incompleta) |
| `runs_coletados` | inteiro | runs de push do default branch na janela |
| `runs_sucesso` / `runs_falha` / `runs_ignorados` | inteiro | runs por classe |
| `workflows` | inteiro | workflows distintos com runs na janela |
| `cfr_a` | decimal | **proporção (0 a 1)**, `runs_falha / (runs_falha + runs_sucesso)` |
| `episodios` | inteiro | episódios de falha (fechados + censurados) |
| `episodios_fechados` | inteiro | episódios encerrados por um sucesso |
| `episodios_censurados` | inteiro | episódios sem sucesso até o fim da janela |
| `proporcao_censurados` | decimal | **proporção (0 a 1)**, `episodios_censurados / episodios` |
| `workflows_falha_sem_sucesso_anterior` | inteiro | workflows cujas primeiras execuções na janela falharam (não abrem episódio) |
| `tempo_recuperacao_mediana_horas` | decimal | **horas**, mediana de `duracao_horas` dos episódios fechados |

## Releases corretivas e CFR (b) (issue #10, Sprint 2)

Etapa `corretivas` do pipeline. **Ela não roda no comando padrão**: quem rotula a amostra-ouro não pode ver a saída da heurística antes de commitar os próprios rótulos (rotulagem cega, issue #10). Depois da rotulagem:

```bash
python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01 --etapas corretivas
python src/avaliar_heuristica.py        # P/R/F1 contra validacao/consenso.csv
```

- Uma release R **falha** se uma release **corretiva** cuja predecessora é R for publicada em até **7 dias**; releases dos **últimos 7 dias** da janela são **censuradas** (fora do denominador).
- **Predecessora**, em duas variantes: `linha` (padrão), que é a maior versão menor ou igual com o mesmo prefixo de tag e trata linhas paralelas (LTS/stable) e monorepos; e `cronologico`, a publicada imediatamente antes, como no lead time.
- **Seis critérios** de release corretiva, entre eles a regra do enunciado (`semver_e_mensagem`: só o patch mudou **e** algum commit tem `fix`/`hotfix`/`revert`). Detalhes, decisões e a tabela de F1 estão em [`docs/heuristica_corretiva.md`](docs/heuristica_corretiva.md).
- **Coleta eficiente:** no pareamento cronológico, os `compare` são os mesmos do lead time e saem do cache. Só os pares da variante `linha` que diferem do cronológico geram chamadas novas (35% das releases na amostra da Sprint 1), e cada `compare` novo baixa no máximo `--max-paginas` páginas de 100 commits (padrão 10). As notas da release vêm da listagem que já está no cache.
- **Resiliência:** um erro inesperado num repositório vira `status` no resumo e a etapa continua; token inválido e `Ctrl+C` interrompem, e o cache permite retomar.

| Arquivo | Conteúdo |
|---|---|
| `releases_corretivas.csv` | Uma linha por release da janela × pareamento, com as características e a decisão de cada critério |
| `cfr_entrega_repos.csv` | Uma linha por repositório × pareamento × critério, com o CFR (b) |
| `validacao/avaliacao_heuristica.csv` / `.md` | P, R e F1 de cada versão da heurística (gerado por `avaliar_heuristica.py`) |
| `validacao/erros_heuristica.csv` | Falsos positivos e negativos de cada versão, para o refinamento |

### Dicionário de dados

`releases_corretivas.csv`: uma linha por release publicada na janela e por pareamento.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `tag_name` / `published_at` | texto / data-hora ISO | campos da release |
| `pareamento` | texto | `linha` ou `cronologico` |
| `predecessora` | texto | tag da predecessora (vazio = primeira da linha ou da história) |
| `tipo_mudanca` | texto | `major`, `minor`, `patch`, `sufixo`, `igual`, `regressao` ou vazio (sem versão, prefixos diferentes ou versão por calendário) |
| `status_compare` | texto | `ok`, `sem_predecessora`, `tag_404` ou `erro_http_<código>` |
| `n_commits` | inteiro | commits de `compare/{predecessora}...{tag_name}` coletados |
| `total_commits_api` | inteiro | `total_commits` informado pelo `compare` |
| `commits_truncados` | sim/nao | `n_commits < total_commits_api` (limite de `--max-paginas`) |
| `n_merges` | inteiro | títulos que começam com `Merge ` |
| `n_fix` | inteiro | títulos com `fix`, `hotfix` ou `revert` como palavra inteira |
| `n_fix_amplo` | inteiro | títulos com as variantes amplas (`fixes`, `bugfix`, `reverted`…), sem merges |
| `n_fix_deps` | inteiro | títulos de `n_fix` que são atualização de dependência |
| `notas_mencionam_correcao` | sim/nao | nome ou notas da release com as palavras amplas |
| `corretiva_<critério>` | sim/nao/vazio | decisão de cada critério (vazio = indeterminado) |
| `situacao_cfr` | texto | `falhou`, `nao_falhou` ou `censurada`, pelo critério padrão (`semver_e_mensagem`) |

`cfr_entrega_repos.csv`: uma linha por repositório, pareamento e critério.

| Coluna | Tipo | Unidade / origem |
|---|---|---|
| `full_name` | texto | `owner/repo` |
| `status` | texto | `ok`, `erro_http_<código>` (listagem de releases) ou `erro: <mensagem>` |
| `pareamento` / `criterio` | texto | versão da heurística |
| `cfr_b` | decimal | **proporção (0 a 1)**, `releases_falharam / releases_avaliadas` (vazio sem releases avaliadas) |
| `releases_avaliadas` | inteiro | releases da janela publicadas até 7 dias antes do fim dela |
| `releases_falharam` | inteiro | releases avaliadas seguidas, em até 7 dias, por uma corretiva que as corrige |
| `releases_censuradas` | inteiro | releases dos últimos 7 dias da janela |
| `releases_corretivas` | inteiro | releases da janela que o critério marcou como corretivas |
| `releases_indeterminadas` | inteiro | releases da janela em que o critério ficou indeterminado (contam como não corretivas) |
| `compares_404` / `compares_erro` / `compares_truncados` | inteiro | problemas na coleta dos commits |

## Testes

```bash
pip install -r requirements.txt
pytest --cov=metricas --cov-report=term-missing
```

O workflow `.github/workflows/ci.yml` roda os testes a cada push e pull request e falha se a cobertura do módulo `metricas` ficar abaixo de 80%.

## Notas metodológicas

- O funil mostra **candidatos coletados** e **avaliados** separadamente, porque a avaliação para ao atingir o alvo.
- A busca usa `pushed:>=<início da janela>` só para reduzir chamadas. Isso não descarta repositórios que passariam nos critérios, pois quem tem runs de push na janela tem `pushed_at` igual ou posterior ao início dela.
- A contagem de runs usa o `total_count` da API, com uma consulta por valor de `conclusion`.
- O pipeline usa a **mesma janela** em todas as etapas.
- A contagem de runs da seleção (`valid_runs_in_window`) usa o `total_count` por valor de `conclusion` e não inclui `startup_failure` (a API não aceita esse valor no filtro). A etapa `runs` baixa os runs um a um e inclui esse caso, então os números podem diferir um pouco.
