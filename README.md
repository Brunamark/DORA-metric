# Lab03 · Mineração de métricas DORA

Pipeline de coleta para o Lab03. Esta etapa (Sprint 1, Card A) faz a **seleção de repositórios**, gera o **funil de seleção** e coleta os **metadados** de cada repositório.

## Requisitos

- Python 3.10+
- Dependência: `requests`
- Token do GitHub (Personal Access Token). Para repositórios públicos, não precisa de nenhum escopo.

## Instalação

```bash
git clone <url-do-repositorio-do-grupo>
cd <pasta-do-repositorio>

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt  # contém: requests
```

## Token do GitHub

O token é lido da variável de ambiente `GITHUB_TOKEN`. **Nunca commite o token.**

```bash
export GITHUB_TOKEN=ghp_seu_token      # Linux/macOS
set GITHUB_TOKEN=ghp_seu_token         # Windows (cmd)
$env:GITHUB_TOKEN="ghp_seu_token"      # Windows (PowerShell)
```

## Como rodar

Comando único, com a janela de observação (12 meses) definida pelo professor:

```bash
python selecao_repos.py --inicio AAAA-MM-DD --fim AAAA-MM-DD
```

Teste rápido antes da coleta completa:

```bash
python selecao_repos.py --inicio AAAA-MM-DD --fim AAAA-MM-DD --alvo 5
```

### Parâmetros

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--inicio` | (obrigatório) | Início da janela, `AAAA-MM-DD` |
| `--fim` | (obrigatório) | Fim da janela, `AAAA-MM-DD` |
| `--alvo` | `100` | Nº de repositórios da amostra |
| `--min-releases` | `5` | Mínimo de releases publicadas na janela |
| `--min-runs` | `50` | Mínimo de workflow runs válidos (push, default branch) |
| `--seed` | `42` | Seed do embaralhamento (reprodutibilidade) |
| `--faixas` | 6 faixas de 1.000 a >60.000 estrelas | Faixas de estrelas da busca (`1000..2000`, `>60000`…) |
| `--saida` | `data` | Pasta dos CSVs de saída |
| `--cache` | `.cache/github` | Pasta do cache de respostas da API |

## O que o script faz

- Busca candidatos fatiando por faixas de estrelas (a busca retorna no máximo 1.000 resultados por consulta).
- Embaralha os candidatos com seed fixa e avalia um a um até atingir o alvo.
- Aplica os filtros, nesta ordem:
  - usa GitHub Actions;
  - tem ≥ 5 releases publicadas na janela (`draft = false`, `prerelease = false`);
  - tem ≥ 50 workflow runs válidos no default branch, com `event = push` e `conclusion` em `success`, `failure`, `timed_out` ou `startup_failure`.
- Coleta estrelas, linguagem, contribuidores, idade e `default_branch`.

## Saídas (pasta `data/`)

| Arquivo | Conteúdo |
|---|---|
| `repos_selecionados.csv` | Amostra final com os metadados |
| `descartados.csv` | Repositórios descartados e o motivo |
| `funil.csv` / `funil.md` | Funil de seleção (vai para a Metodologia do artigo) |

### Colunas de `repos_selecionados.csv`

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

- Toda resposta da API é salva em `.cache/github/`.
- Se o script for interrompido (`Ctrl+C`, queda de rede, rate limit), **rode o mesmo comando de novo**: ele continua de onde parou, sem repetir chamadas.
- Para refazer a coleta do zero, apague a pasta `.cache/`.
- Adicione `.cache/` e `data/` ao `.gitignore` se não quiser versioná-los.

## Rate limit e erros

- O script lê `X-RateLimit-Remaining` e `X-RateLimit-Reset` e **espera sozinho** quando a cota acaba. A busca tem cota própria, menor, então pausas nessa etapa são normais.
- Erros 5xx e falhas de rede são repetidos com backoff exponencial (1, 2, 4, 8, 16 s).

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Defina a variável de ambiente GITHUB_TOKEN` | Token não exportado | Exporte o token no terminal atual |
| HTTP 401 / `Bad credentials` | Token inválido ou expirado | Gere um novo token |
| `só N aprovados de 100` | Poucos candidatos passaram nos filtros | Amplie as faixas com `--faixas` |
| Aviso de faixa com mais de 1.000 resultados | A faixa de estrelas é larga demais | Divida a faixa em intervalos menores |
| Execução lenta | Rate limit da busca ou da API | Deixe rodando; o cache preserva o progresso |

## Releases, commits entre releases e lead time (Card B, issue #2)

Depois da seleção, rode a coleta de releases com a **mesma janela**:

```bash
cd src
python coleta_releases.py --inicio 2025-10-01 --fim 2026-10-01
```

- Deploy = release publicada (`draft = false`, `prerelease = false`). A primeira release do histórico não tem anterior e é ignorada.
- Para cada release da janela, os commits entregues vêm de `/compare/{anterior}...{release}`, seguindo a paginação até o fim. Tag inexistente ou reescrita (HTTP 404) pula a release e entra na contagem `releases_404`.
- O lead time usa a data de autoria do commit (`commit.author.date`), em **dias**:
  - variante (a), `lead_time_release()`: release − commit mais antigo; o valor do repositório é a mediana entre as releases;
  - variante (b), `lead_time_commit()`: release − cada commit; o valor do repositório é a mediana de todos os commits.

| Arquivo | Conteúdo |
|---|---|
| `releases.csv` | Todas as releases listadas, com `status` (`ok`, `sem_commits`, `tag_404`, `primeira_release`, `fora_da_janela`, `excluida_draft`, `excluida_prerelease`) |
| `commits_releases.csv` | Commits entregues por release e o lead time de cada um |
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
- Use a **mesma janela** nas coletas de releases, commits e workflow runs do grupo.
