# Dicionário de dados

Documenta **todas as colunas de todos os CSVs** gerados pelo pipeline (issue #8). Cada coluna tem nome, tipo, unidade e fórmula ou origem na API do GitHub.

Convenções:
- **Janela de observação:** de 01/10/2025 00:00:00 a 01/10/2026 23:59:59 (UTC), igual em todas as etapas.
- **Datas:** ISO 8601 em UTC, como a API devolve (ex.: `2026-03-15T10:00:00Z`).
- **Valores vazios:** a métrica não pôde ser calculada, porque o repositório falta na fonte, a coleta deu erro ou não houve dados. O motivo aparece nas colunas `status_*`.
- **Proporções:** de 0 a 1, e não em %.
- **Unidades das métricas:** a frequência de deploy é em releases por semana (a janela tem ≈ 52,3 semanas), o lead time em **dias** e o tempo de recuperação em **horas**.
- **Booleanos:** `True`/`False`, exceto onde a tabela indica `sim`/`nao`.

| Arquivo | Etapa (script) | Granularidade | Versionado? |
|---|---|---|---|
| [`dataset.csv`](#datasetcsv) | `consolidar` (`consolidar.py`) | repositório | sim |
| [`repos_selecionados.csv`](#repos_selecionadoscsv) | `selecao` (`selecao_repos.py`) | repositório | sim |
| [`descartados.csv`](#descartadoscsv) | `selecao` | repositório descartado | sim |
| [`funil.csv`](#funilcsv) / `funil.md` | `selecao` | etapa do funil | sim |
| [`releases.csv`](#releasescsv) | `releases` (`coleta_releases.py`) | release | sim |
| [`commits_releases.csv`](#commits_releasescsv) | `releases` | commit × release | **não** (> 250 MB; regerado pelo pipeline) |
| [`tags.csv`](#tagscsv) | `releases` + `variantes` | tag | sim |
| [`lead_time_repos.csv`](#lead_time_reposcsv) | `releases` | repositório | sim |
| [`releases_c2.csv`](#releases_c2csv) | `variantes` (`variantes.py`) | release ou pré-release | sim |
| [`variantes_repos.csv`](#variantes_reposcsv) | `variantes` | repositório | sim |
| [`runs.csv`](#runscsv) | `runs` (`coleta_runs.py`) | workflow run | **não** (> 100 MB com 350 repositórios; regerado pelo pipeline) |
| [`episodios.csv`](#episodioscsv) | `runs` | episódio de falha | sim |
| [`runs_fatias.csv`](#runs_fatiascsv) | `runs` | consulta à API | sim |
| [`workflow_runs_repos.csv`](#workflow_runs_reposcsv) | `runs` | repositório | sim |
| [`releases_corretivas.csv`](#releases_corretivascsv) | `corretivas` (`corretivas.py`) | release × pareamento | sim |
| [`cfr_entrega_repos.csv`](#cfr_entrega_reposcsv) | `corretivas` | repositório × pareamento × critério | sim |

Todos os arquivos ficam em `src/data/`. Os arquivos da validação manual (`validacao/`) estão na [última seção](#validação-manual-pasta-validacao).

---

## `dataset.csv`

Dataset consolidado: **uma linha por repositório da amostra final**, com todas as variantes das métricas. É a entrada das análises da Sprint 3. A junção com as outras fontes é pela esquerda: um repositório que falta numa fonte continua no arquivo, com as métricas vazias.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` (`repos_selecionados.csv`) |
| `url` | texto | — | `html_url` do repositório |
| `stars` | inteiro | estrelas | `stargazers_count` |
| `language` | texto | — | linguagem principal (`language`) |
| `contributors` | inteiro | pessoas | nº de contribuidores (`/contributors?per_page=1&anon=true`, última página do header `Link`) |
| `created_at` | data/hora | — | criação do repositório |
| `age_days` | inteiro | dias | `fim da janela − created_at` |
| `default_branch` | texto | — | branch principal |
| `releases_na_janela` | inteiro | releases | releases publicadas (`draft = false`, `prerelease = false`) com `published_at` na janela (`lead_time_repos.csv`) |
| `releases_na_janela_c2` | inteiro | releases | releases não draft (publicadas **e** pré-releases) com `published_at` na janela (`variantes_repos.csv`) |
| `tags_na_janela` | inteiro | tags | tags de `tags.csv` com `commit_date` na janela; tag sem data não conta |
| `freq_deploy_release` | decimal | releases/semana | **RQ 01, C1:** `releases_na_janela ÷ semanas da janela` (`metricas.frequencia_deploy`). Vazio se `status_releases ≠ ok` |
| `freq_deploy_release_pre` | decimal | releases/semana | **C2:** `releases_na_janela_c2 ÷ semanas da janela`. Vazio se `status_releases_c2 ≠ ok` |
| `freq_deploy_tag` | decimal | tags/semana | **C3:** `tags_na_janela ÷ semanas da janela`. Vazio se `status_tags` ou `status_tags_datas ≠ ok` |
| `lead_time_a_dias` | decimal | dias | **RQ 02 (a), C1:** mediana, entre as releases, de `published_at − min(commit.author.date)` |
| `lead_time_b_dias` | decimal | dias | **RQ 02 (b), C1:** mediana de `published_at − commit.author.date` de todos os commits de todas as releases |
| `lead_time_a_dias_c2` | decimal | dias | lead time (a) com release + pré-release como unidade de deploy |
| `lead_time_b_dias_c2` | decimal | dias | lead time (b) com release + pré-release como unidade de deploy |
| `cfr_a` | decimal | proporção | **RQ 03 (a):** `runs com falha ÷ (falhas + sucessos)`, runs de `push` no default branch |
| `tempo_recuperacao_horas` | decimal | horas | **RQ 04:** mediana da duração dos episódios de falha fechados, de todos os workflows |
| `episodios` | inteiro | episódios | episódios de falha (fechados + censurados) |
| `episodios_censurados` | inteiro | episódios | episódios sem sucesso até o fim da janela |
| `proporcao_censurados` | decimal | proporção | `episodios_censurados ÷ episodios` |
| `status_releases` | texto | — | `ok` ou `erro_http_<código>` ao listar as releases |
| `status_tags` | texto | — | `ok` ou `erro_http_<código>` ao listar as tags (REST) |
| `status_releases_c2` | texto | — | `ok` ou `erro_http_<código>` ao listar as releases na etapa `variantes` |
| `status_tags_datas` | texto | — | `ok`, `erro_http_<código>` ou `erro_graphql_<tipo>` ao consultar as datas das tags |
| `status_runs` | texto | — | `ok` ou `erro_http_<código>` ao listar os runs |
| `releases_404` | inteiro | releases | releases da C1 puladas porque o `compare` retornou 404 (tag apagada ou reescrita) |
| `releases_404_c2` | inteiro | releases | o mesmo, na C2 |
| `tags` | inteiro | tags | tags do repositório em `tags.csv` |
| `tags_sem_data` | inteiro | tags | tags sem `commit_date` (sha inexistente ou que não aponta para commit) |
| `fatias_no_teto` | inteiro | consultas | consultas de runs que ficaram no teto de 1.000 resultados (≠ 0 indica contagem incompleta) |
| `cfr_b` | decimal | proporção | **RQ 03 (b)**, só com `--incluir-cfr-b`: `releases que falharam ÷ releases avaliadas`, com a versão padrão da heurística (`PAREAMENTO_PADRAO` e `CRITERIO_PADRAO` de `metricas.py`) |
| `releases_avaliadas_cfr_b` | inteiro | releases | só com `--incluir-cfr-b`: releases da janela publicadas até 7 dias antes do fim dela |
| `releases_censuradas_cfr_b` | inteiro | releases | só com `--incluir-cfr-b`: releases dos últimos 7 dias da janela (fora do denominador) |
| `status_cfr_b` | texto | — | só com `--incluir-cfr-b`: `status` de `cfr_entrega_repos.csv` |

A classificação DORA (Elite/High/Medium/Low) **não** está no dataset. As análises a calculam a partir dele com `metricas.classificar` e `metricas.classificacao_geral`, nas combinações C1, C2 e C3 da RQ 07.

---

## `repos_selecionados.csv`

Amostra final: uma linha por repositório aprovado em todos os filtros.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `url` | texto | — | `html_url` do repositório |
| `stars` | inteiro | estrelas | `stargazers_count` |
| `language` | texto | — | linguagem principal (`language`) |
| `contributors` | inteiro | pessoas | última página de `/contributors?per_page=1&anon=true` |
| `created_at` | data/hora | — | criação do repositório |
| `age_days` | inteiro | dias | de `created_at` até o fim da janela |
| `default_branch` | texto | — | branch principal |
| `releases_in_window` | inteiro | releases | releases publicadas dentro da janela (`/releases`, `draft = false`, `prerelease = false`) |
| `valid_runs_in_window` | inteiro | runs | runs válidos na janela: soma dos `total_count` de `/actions/runs?branch&event=push&status=<conclusion>` para `success`, `failure`, `timed_out` e `startup_failure` (este último é ignorado quando a API recusa o filtro com 422) |

## `descartados.csv`

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `motivo` | texto | — | `sem_actions`, `menos_de_5_releases`, `menos_de_50_runs_validos` ou `erro_api_<endpoint>` |

## `funil.csv`

Mesma tabela de `funil.md`, que vai para a Metodologia.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `etapa` | texto | — | candidatos coletados, avaliados, usam Actions, ≥ 5 releases, ≥ 50 runs, amostra final |
| `restantes` | inteiro | repositórios | repositórios que passaram da etapa |
| `descartados` | inteiro | repositórios | repositórios descartados na etapa (vazio na primeira e na última linha) |
| `motivo` | texto | — | motivo do descarte da etapa |

---

## `releases.csv`

Uma linha por release listada em `/repos/{owner}/{repo}/releases`. A paginação para quando chega a releases anteriores à janela, com uma folga para achar a anterior.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `tag_name` | texto | — | `tag_name` da release |
| `draft` / `prerelease` | booleano | — | campos `draft` e `prerelease` da release |
| `published_at` | data/hora | — | `published_at` da release (vazio em drafts) |
| `na_janela` | booleano | — | release publicada com `published_at` dentro da janela |
| `tag_anterior` | texto | — | tag da release publicada imediatamente anterior (base do `compare`) |
| `status` | texto | — | `ok`, `sem_commits`, `tag_404`, `erro_http_<código>`, `primeira_release`, `fora_da_janela`, `excluida_draft` ou `excluida_prerelease` |
| `n_commits` | inteiro | commits | commits entregues (`/compare/{tag_anterior}...{tag_name}`, paginado até o fim) |
| `total_commits_api` | inteiro | commits | `total_commits` informado pelo `compare`; diferente de `n_commits` indica comparação incompleta |
| `lead_time_release_dias` | decimal | dias | `published_at − min(commit.author.date)`, variante (a) |

## `commits_releases.csv`

Uma linha por commit entregue numa release com `status = ok`. Não é versionado: é regerado pelo pipeline a partir do cache.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `tag_name` | texto | — | release que entregou o commit |
| `sha` | texto | — | `sha` do commit |
| `author_date` | data/hora | — | `commit.author.date` |
| `lead_time_dias` | decimal | dias | `published_at − commit.author.date`, variante (b) |
| `mensagem` | texto | — | primeira linha de `commit.message` (até 300 caracteres) |

## `tags.csv`

Uma linha por tag: unidade de deploy da combinação C3. A etapa `releases` grava as três primeiras colunas, e a etapa `variantes` regrava o arquivo com `commit_date`.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `tag_name` | texto | — | `name` da tag (REST `/tags`) |
| `sha` | texto | — | `commit.sha` apontado pela tag (REST `/tags`) |
| `commit_date` | data/hora | — | `committedDate` do commit apontado (GraphQL `repository.object(oid:)`); vazio se o sha não existe mais ou não é um commit |

## `lead_time_repos.csv`

Uma linha por repositório.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `status_releases` | texto | — | `ok` ou `erro_http_<código>` ao listar as releases |
| `status_tags` | texto | — | `ok` ou `erro_http_<código>` ao listar as tags |
| `releases_na_janela` | inteiro | releases | releases publicadas (sem draft e sem pré-release) dentro da janela |
| `releases_calculadas` | inteiro | releases | releases da janela com lead time calculado (`status = ok`) |
| `releases_sem_commits` | inteiro | releases | releases da janela sem commits novos |
| `releases_404` | inteiro | releases | releases puladas porque o `compare` retornou 404 |
| `releases_erro` | inteiro | releases | releases puladas por outro erro HTTP no `compare` |
| `releases_commits_incompletos` | inteiro | releases | releases em que `n_commits ≠ total_commits_api` |
| `commits` | inteiro | commits | commits entregues pelas releases calculadas |
| `commits_lead_time_negativo` | inteiro | commits | commits com `commit.author.date` posterior à release (mantidos no cálculo) |
| `lead_time_release_mediana_dias` | decimal | dias | mediana de `lead_time_release_dias`, variante (a) |
| `lead_time_commit_mediana_dias` | decimal | dias | mediana de `lead_time_dias` de todos os commits, variante (b) |

---

## `releases_c2.csv`

Combinação C2 (release + pré-release). Uma linha por release não draft, publicada ou pré-release, com `published_at` na janela. O par é a release não draft imediatamente anterior, por `published_at`.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `tag_name` | texto | — | `tag_name` da release |
| `prerelease` | booleano | — | campo `prerelease` da release |
| `published_at` | data/hora | — | `published_at` da release |
| `tag_anterior` | texto | — | tag da release não draft imediatamente anterior (base do `compare`) |
| `status` | texto | — | `ok`, `sem_commits`, `tag_404`, `erro_http_<código>` ou `primeira_release` |
| `n_commits` | inteiro | commits | commits de `/compare/{tag_anterior}...{tag_name}` |
| `total_commits_api` | inteiro | commits | `total_commits` informado pelo `compare` |
| `lead_time_release_dias` | decimal | dias | `published_at − min(commit.author.date)`, variante (a) da C2 |

## `variantes_repos.csv`

Uma linha por repositório.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `status_releases_c2` | texto | — | `ok` ou `erro_http_<código>` ao listar as releases |
| `releases_na_janela_c2` | inteiro | releases | releases não draft (publicadas e pré-releases) dentro da janela |
| `releases_calculadas_c2` | inteiro | releases | releases da janela com lead time calculado |
| `releases_sem_commits_c2` | inteiro | releases | releases da janela sem commits novos |
| `releases_404_c2` | inteiro | releases | releases puladas porque o `compare` retornou 404 |
| `releases_erro_c2` | inteiro | releases | releases puladas por outro erro HTTP no `compare` |
| `releases_commits_incompletos_c2` | inteiro | releases | releases em que `n_commits ≠ total_commits_api` |
| `commits_c2` | inteiro | commits | commits entregues pelas releases calculadas |
| `commits_lead_time_negativo_c2` | inteiro | commits | commits com data posterior à release (mantidos no cálculo) |
| `lead_time_release_mediana_dias_c2` | decimal | dias | mediana de `lead_time_release_dias` da C2, variante (a) |
| `lead_time_commit_mediana_dias_c2` | decimal | dias | mediana do lead time de todos os commits da C2, variante (b) |
| `status_tags_datas` | texto | — | `ok`, `erro_http_<código>` ou `erro_graphql_<tipo>` ao consultar as datas |
| `tags` | inteiro | tags | tags do repositório em `tags.csv` |
| `tags_sem_data` | inteiro | tags | tags com `commit_date` vazio |

---

## `runs.csv`

Uma linha por workflow run do default branch com `event = push` e `created_at` na janela (`/actions/runs?branch=…&event=push&created=…`, consulta por mês). Não é versionado: é regerado pelo pipeline a partir do cache.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `run_id` | inteiro | — | `id` do run |
| `workflow_id` | inteiro | — | `workflow_id` do run (agrupa os episódios) |
| `workflow_name` | texto | — | `name` do run |
| `conclusion` | texto | — | `conclusion` do run (vazio = em andamento) |
| `classe` | texto | — | `sucesso` (`success`), `falha` (`failure`, `timed_out`, `startup_failure`) ou `ignorado` (demais) |
| `created_at` | data/hora | — | `created_at`: ordena os runs e define se o run está na janela |
| `run_started_at` | data/hora | — | `run_started_at`: início de um episódio |
| `updated_at` | data/hora | — | `updated_at`: fim do run que encerra um episódio |
| `run_attempt` | inteiro | tentativas | `run_attempt` (re-runs mantêm o mesmo `run_id`) |

## `episodios.csv`

Uma linha por episódio de falha. Um episódio começa na primeira falha após um sucesso e termina no próximo sucesso do mesmo workflow.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `workflow_id` | inteiro | — | workflow em que o episódio ocorreu |
| `run_inicio` / `run_fim` | inteiro | — | `run_id` da primeira falha / do sucesso que encerrou o episódio (vazio se censurado) |
| `inicio` | data/hora | — | `run_started_at` da primeira falha (`created_at` se vier vazio) |
| `fim` | data/hora | — | `updated_at` do sucesso (vazio se censurado) |
| `n_falhas` | inteiro | runs | runs com falha dentro do episódio |
| `censurado` | booleano | — | `True` se não houve sucesso até o fim da janela |
| `duracao_horas` | decimal | horas | `fim − inicio` (vazio se censurado) |

## `runs_fatias.csv`

Uma linha por consulta de runs. A janela é dividida em meses, e um mês que atinge 1.000 resultados é dividido ao meio até caber.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `inicio` / `fim` | data/hora | — | limites do filtro `created` da consulta |
| `total_count` | inteiro | runs | `total_count` informado pela API |
| `dividida` | booleano | — | a fatia atingiu 1.000 e foi dividida em duas |
| `no_teto` | booleano | — | a fatia atingiu 1.000 e não pôde ser dividida (contagem incompleta) |
| `status` | texto | — | `ok` ou `erro_http_<código>` |

## `workflow_runs_repos.csv`

Uma linha por repositório.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `default_branch` | texto | — | branch consultado |
| `status_runs` | texto | — | `ok` ou `erro_http_<código>` |
| `fatias_consultadas` | inteiro | consultas | consultas feitas (13 meses-calendário + divisões) |
| `fatias_divididas` | inteiro | consultas | consultas que atingiram 1.000 e foram divididas |
| `fatias_no_teto` | inteiro | consultas | consultas que ficaram no teto (≠ 0 indica contagem incompleta) |
| `runs_coletados` | inteiro | runs | runs de push do default branch na janela |
| `runs_sucesso` / `runs_falha` / `runs_ignorados` | inteiro | runs | runs por classe |
| `workflows` | inteiro | workflows | workflows distintos com runs na janela |
| `cfr_a` | decimal | proporção | `runs_falha ÷ (runs_falha + runs_sucesso)` |
| `episodios` | inteiro | episódios | episódios de falha (fechados + censurados) |
| `episodios_fechados` | inteiro | episódios | episódios encerrados por um sucesso |
| `episodios_censurados` | inteiro | episódios | episódios sem sucesso até o fim da janela |
| `proporcao_censurados` | decimal | proporção | `episodios_censurados ÷ episodios` |
| `workflows_falha_sem_sucesso_anterior` | inteiro | workflows | workflows cujas primeiras execuções na janela falharam (não abrem episódio) |
| `tempo_recuperacao_mediana_horas` | decimal | horas | mediana de `duracao_horas` dos episódios fechados |

---

## `releases_corretivas.csv`

Uma linha por release publicada na janela e por pareamento (`linha` ou `cronologico`). Gerado só por `--etapas corretivas`, depois das rotulagens da amostra-ouro.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `tag_name` / `published_at` | texto / data/hora | — | campos da release |
| `pareamento` | texto | — | `linha` (maior versão anterior com o mesmo prefixo de tag) ou `cronologico` (publicada imediatamente antes) |
| `predecessora` | texto | — | tag da predecessora (vazio = primeira da linha ou da história) |
| `tipo_mudanca` | texto | — | `major`, `minor`, `patch`, `sufixo`, `igual`, `regressao` ou vazio (sem versão SemVer, prefixos diferentes ou versão por calendário) |
| `status_compare` | texto | — | `ok`, `sem_predecessora`, `tag_404` ou `erro_http_<código>` |
| `n_commits` | inteiro | commits | commits de `/compare/{predecessora}...{tag_name}` coletados |
| `total_commits_api` | inteiro | commits | `total_commits` informado pelo `compare` |
| `commits_truncados` | sim/nao | — | `n_commits < total_commits_api` (limite de `--max-paginas`) |
| `n_merges` | inteiro | commits | títulos que começam com `Merge ` |
| `n_fix` | inteiro | commits | títulos com `fix`, `hotfix` ou `revert` como palavra inteira |
| `n_fix_amplo` | inteiro | commits | títulos com as variantes amplas (`fixes`, `bugfix`, `reverted`…), sem merges |
| `n_fix_deps` | inteiro | commits | títulos de `n_fix` que são atualização de dependência |
| `notas_mencionam_correcao` | sim/nao | — | nome ou notas da release (`name`, `body`) com as palavras amplas |
| `corretiva_<critério>` | sim/nao/vazio | — | decisão de cada critério da heurística (vazio = indeterminado); critérios em `docs/heuristica_corretiva.md` |
| `situacao_cfr` | texto | — | `falhou`, `nao_falhou` ou `censurada`, pelo critério padrão |

## `cfr_entrega_repos.csv`

Uma linha por repositório, pareamento e critério.

| Coluna | Tipo | Unidade | Fórmula / origem |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` |
| `status` | texto | — | `ok`, `erro_http_<código>` (listagem de releases) ou `erro: <mensagem>` |
| `pareamento` / `criterio` | texto | — | versão da heurística |
| `cfr_b` | decimal | proporção | `releases_falharam ÷ releases_avaliadas` (vazio sem releases avaliadas) |
| `releases_avaliadas` | inteiro | releases | releases da janela publicadas até 7 dias antes do fim dela |
| `releases_falharam` | inteiro | releases | releases avaliadas seguidas, em até 7 dias, por uma corretiva que as corrige |
| `releases_censuradas` | inteiro | releases | releases dos últimos 7 dias da janela |
| `releases_corretivas` | inteiro | releases | releases da janela que o critério marcou como corretivas |
| `releases_indeterminadas` | inteiro | releases | releases em que o critério ficou indeterminado (contam como não corretivas) |
| `compares_404` / `compares_erro` / `compares_truncados` | inteiro | releases | problemas na coleta dos commits |

---

## Validação manual (pasta `validacao/`)

Gerados pelos scripts da amostra-ouro (issues #9 e #10), fora do pipeline de coleta.

| Arquivo | Colunas | Conteúdo |
|---|---|---|
| `amostra_ouro.csv` | `repo`, `tag`, `tag_anterior` | as 60 × 5 releases sorteadas (seed 42) |
| `rotulos_<integrante>.csv` | `repo`, `tag`, `tag_anterior`, `link_repo`, `link_release`, `link_commits`, `tipo_projeto`, `releases_reais`, `corretiva` | planilha de rótulos de cada avaliador; valores permitidos: `tipo_projeto` ∈ {biblioteca/framework, aplicação/serviço, ferramenta CLI, outro}, `releases_reais` ∈ {sim, não, incerto}, `corretiva` ∈ {sim, não} |
| `kappa.csv` | `dimensao`, `n_itens`, `n_avaliadores`, `n_categorias_usadas`, `pct_itens_unanimes` (%), `kappa`, `interpretacao` | kappa de Fleiss por dimensão, com a interpretação de Landis & Koch (1977) |
| `consenso.csv` | `dimensao`, `repo`, `tag`, `votos`, `rotulo_consenso`, `decidido_em` (`maioria` ou `reuniao`) | rótulo de referência de cada item |
| `avaliacao_heuristica.csv` | `versao`, `pareamento`, `criterio`, `n`, `vp`, `fp`, `fn`, `vn`, `indeterminadas`, `precisao`, `recall`, `f1` | P/R/F1 de cada versão da heurística contra o consenso |
| `erros_heuristica.csv` | `versao`, `erro` (`falso_positivo`/`falso_negativo`), `full_name`, `tag_name`, `predecessora`, `tipo_mudanca`, `n_commits`, `n_fix`, `n_fix_amplo`, `n_fix_deps`, `notas_mencionam_correcao` | falsos positivos e negativos de cada versão, para o refinamento |
