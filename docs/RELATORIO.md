# Relatório — Mineração de Métricas DORA em Repositórios Open-Source

**Disciplina:** Laboratório de Experimentação de Software · **Laboratório 03** · Prof. Danilo Maia
**Amostra:** 350 repositórios públicos do GitHub com GitHub Actions · **Janela de observação:** 01/10/2025 a 01/10/2026 (12 meses)

---

## Sumário executivo

Calculamos as quatro métricas DORA (frequência de deploy, lead time, taxa de falha e tempo de recuperação) para 350 repositórios populares e perguntamos **o quanto podemos confiar nesses números**, já que todos são *proxies* (release ≠ deploy; falha de CI ≠ falha em produção). Os cinco achados principais:

1. **O repositório típico é "Medium" DORA.** Mediana de 0,40 release/semana, lead time de ~11 dias, falha de CI de ~6% e recuperação em ~2,9 h. Só 6 de 350 repositórios entregam ≥ 7 vezes por semana.
2. **A estabilidade de CI é excelente e a velocidade de entrega é modesta.** 81% dos repositórios têm falha de CI ≤ 15% (faixa Elite); mas 30% publicam menos de 1 release por mês (faixa Low).
3. **Velocidade e estabilidade NÃO estão em trade-off quando medimos estabilidade por CI** (Spearman ρ = 0,08; p = 0,13; n = 350). Isso concorda com a tese do DORA.
4. **A conclusão se inverte com outra definição de falha.** Com o proxy de entrega (release seguida de um *patch* em ≤ 7 dias), ρ = +0,54 (mais releases → "mais falhas"). Mostramos que boa parte disso é **efeito mecânico da heurística**: quem publica muito tem mais chance de publicar algo em 7 dias, independentemente de qualquer defeito. A validação contra a amostra-ouro confirma: das releases que essa regra trata como corretivas, **44% não são** (precisão 0,56; F1 0,52, abaixo do mínimo de 0,70).
5. **A classificação DORA de um repositório depende da definição operacional.** Entre 14% e 33% dos repositórios mudam de categoria conforme a combinação de definições escolhida (kappa ponderado de 0,47 a 0,80). A idade do repositório é o fator que mais se associa às métricas; as estrelas não explicam nada.

---

## 1. Contexto e problema

O DORA define quatro métricas de desempenho de entrega: duas de **velocidade** (*deployment frequency*, *lead time for changes*) e duas de **estabilidade** (*change failure rate*, tempo de recuperação). O GitHub não registra deploys nem falhas em produção, então inferimos:

| Conceito DORA | Proxy usado aqui |
|---|---|
| Deploy | Release publicada (`draft = false`, `prerelease = false`) |
| Lead time (a) | Data da release − data do commit **mais antigo** incluído nela (mediana por repositório) |
| Lead time (b) | Data da release − data de **cada commit** incluído (mediana de todos os commits) |
| CFR (a) | Execuções de CI com falha ÷ (falhas + sucessos), no default branch, evento `push` |
| CFR (b) | Releases seguidas, em ≤ 7 dias, por uma release que só muda o *patch* (SemVer) ÷ releases avaliadas |
| Recuperação | Do início da 1ª falha de um workflow até o fim da próxima execução bem-sucedida do mesmo workflow |

A pergunta central do laboratório é dupla: *qual é o valor das métricas?* e *quanto esse valor muda quando a definição muda?*

---

## 2. Dados e metodologia

### 2.1 Fonte de dados e seleção

Os dados vêm de repositórios públicos do GitHub, coletados por scripts próprios do grupo com as APIs REST e GraphQL, sem bibliotecas de terceiros de acesso à API. A população-alvo são repositórios populares que usam CI/CD com GitHub Actions.

**Candidatos.** A busca (`/search/repositories`) devolve no máximo 1.000 resultados por consulta, então foi fatiada em seis faixas de estrelas (1.000–2.000, 2.000–5.000, 5.000–10.000, 10.000–25.000, 25.000–60.000 e mais de 60.000), sempre com *push* depois do início da janela (`pushed:>=2025-10-01`). Um repositório sem *push* na janela não pode ter execuções de CI por *push* nela, então o filtro reduz chamadas sem descartar candidatos válidos. A busca resultou em 5.347 candidatos únicos. Como ela é ordenada por estrelas, em cada faixa só os 1.000 mais estrelados viram candidatos; nas cinco faixas abaixo de 60.000 estrelas o total de resultados passou desse teto (16.595, 12.229, 4.764, 2.935 e 1.097, da menor para a maior faixa). Dentro de cada faixa, portanto, a amostra pende para os repositórios mais populares.

**Ordem de avaliação.** Os candidatos foram embaralhados com semente fixa (`seed = 42`) e avaliados um a um até 350 serem aprovados (alvo acima do mínimo de 300, como folga para falhas de coleta). A ordem aleatória evita que a amostra se concentre nos mais populares, e a semente torna a seleção reproduzível. A amostra da Sprint 1 (100 repositórios) são os 100 primeiros aprovados nessa mesma ordem, e por isso está contida na final.

**Critérios de inclusão,** aplicados do mais barato ao mais caro em chamadas à API: (1) o repositório usa GitHub Actions (`/actions/workflows` com `total_count > 0`); (2) tem pelo menos 5 releases publicadas na janela (`draft = false`, `prerelease = false`); (3) tem pelo menos 50 *workflow runs* válidos na janela (no *default branch*, disparados por `push`, com `conclusion` igual a `success`, `failure`, `timed_out` ou `startup_failure`). Cada descarte fica registrado com o motivo (`descartados.csv`).

**Funil de seleção:**

| Etapa | Restantes | Descartados | Motivo |
|---|---:|---:|---|
| Candidatos coletados na busca | 5.347 | | |
| Avaliados (ordem aleatória, semente fixa, até atingir o alvo) | 1.185 | 4.162 | não avaliados (alvo atingido) |
| Usam GitHub Actions | 1.022 | 163 | sem workflows / erro de API |
| ≥ 5 releases publicadas na janela | 437 | 585 | releases insuficientes |
| ≥ 50 workflow runs válidos (push, default branch) | 350 | 87 | runs insuficientes |
| **Amostra final** | **350** | | |

O critério de releases foi o mais restritivo: 57% dos repositórios avaliados com Actions (585 de 1.022) tinham menos de 5 releases na janela. Muitos projetos populares publicam versões só por tags ou por gerenciadores de pacotes, sem releases do GitHub.

**Metadados** (fatores da RQ06): estrelas, linguagem principal, número de contribuidores (lido do número da última página de `/contributors?per_page=1&anon=true`), idade em dias até o fim da janela e *default branch*. A amostra final tem 29 linguagens principais; mediana de 20.272 estrelas (IQR 8.725–35.771), de 216 contribuidores (IQR 81–443) e de 6,7 anos de idade (IQR 2,7–10,6).

### 2.2 Coleta

A coleta é feita por um pipeline em Python, executado com um único comando (`python src/pipeline.py --inicio 2025-10-01 --fim 2026-10-01`), nas etapas seleção, releases, variantes, *workflow runs* e consolidação. Todas usam a mesma janela (1º/10/2025 a 1º/10/2026, UTC) e só o *default branch*.

- **Releases e commits.** As releases vêm de `/releases`, paginadas até passar 90 dias antes do início da janela (o que garante a release anterior à primeira da janela). Os commits entregues por uma release R vêm de `/compare/{anterior}...{R}`, seguindo as páginas de 100 commits até o fim e conferindo com o campo `total_commits` (nenhuma lista ficou incompleta). Comparações com HTTP 404 (tag apagada ou reescrita) foram contadas e excluídas do lead time: 7 releases na definição principal e 9 na variante com pré-releases.
- **Tags.** Vêm de `/tags`; como a API REST não informa a data de uma tag, usamos a data do commit apontado (`committedDate`), consultada pela API GraphQL em lotes de 100. Foram 196.409 tags, todas com data.
- **Workflow runs.** Vêm de `/actions/runs`, filtrados por *branch*, `event=push` e intervalo de criação. Com filtros, a API devolve no máximo 1.000 resultados por consulta, então a janela é consultada mês a mês; um mês que atinge o teto é dividido ao meio (por dias e, dentro de um dia, por horário) até cada parte caber. Foram 6.374 consultas, 912 delas divididas, e **nenhuma parte ficou no teto**. Ao todo, 1.267.028 runs coletados, dos quais 1.189.508 válidos (sucesso ou falha).
- **Cache, retomada e limites.** Toda resposta da API é gravada em disco; uma coleta interrompida é retomada com o mesmo comando, sem repetir chamadas, e a consolidação não faz nenhuma chamada. O pipeline respeita a cota de 5.000 requisições por hora (`X-RateLimit-Remaining`/`Reset`), repete erros 5xx e de rede com *backoff* exponencial (até 5 tentativas) e interrompe em HTTP 401 sem gravar a resposta no cache.
- **Dataset.** Os resumos por repositório são consolidados em `src/data/dataset.csv`, uma linha por repositório com todas as variantes; nenhum repositório terminou com erro de coleta em nenhuma etapa. Cada coluna está documentada em `docs/dicionario_dados.md`.

### 2.3 Definições operacionais

As fórmulas resumidas estão na tabela da seção 1; aqui ficam as decisões que mudam os números.

- **Lead time.** A release anterior de R é a publicada imediatamente antes dela. A data de um commit é a de autoria (`commit.author.date`). Releases sem commits novos em relação à anterior (2.436) e a primeira release de cada repositório (62) ficam fora. Na variante (a), o valor do repositório é a mediana entre as releases; na (b), a mediana de todos os commits de todas as releases.
- **CFR (a).** `success` é sucesso; `failure`, `timed_out` e `startup_failure` são falha; `cancelled`, `skipped`, `neutral`, `action_required`, `stale` e execuções em andamento são ignorados.
- **CFR (b) e release corretiva.** Neste relatório, uma release R falha se, em até 7 dias, sai outra release da mesma linha (mesmo prefixo de tag e mesmo MAJOR.MINOR) com *patch* maior. Releases dos últimos 7 dias da janela ficam fora do denominador (censura), e o repositório precisa de pelo menos 5 releases avaliáveis. Essa regra foi validada contra a amostra-ouro e não atingiu o mínimo (seção 2.6 e RQ03). O pipeline do grupo implementa 14 versões da heurística de release corretiva, combinando dois pareamentos com sete critérios de versão e de mensagem de commit (`docs/heuristica_corretiva.md`). Elas consideram que 78 repositórios (22%) mantêm linhas de versão paralelas, como LTS e estável, e que 44 (13%) são monorepos com mais de um prefixo de tag.
- **Recuperação.** As execuções de cada workflow são ordenadas no tempo. Um episódio começa na primeira falha depois de um sucesso (`run_started_at`) e termina na próxima execução bem-sucedida do **mesmo** workflow (`updated_at`). Falhas antes do primeiro sucesso da janela não abrem episódio, porque o início real está fora dela. O valor do repositório é a mediana dos episódios encerrados.
- **Censura.** Episódios sem sucesso até o fim da janela e releases dos últimos 7 dias não são descartados em silêncio: são contados e reportados (RQ03 e RQ04), porque descartá-los faria os repositórios parecerem mais estáveis e mais rápidos para se recuperar.

### 2.4 O que há nos dados

| Base | Cobertura | Conteúdo |
|---|---|---|
| `repos_selecionados.csv` | 350 repositórios | estrelas, linguagem, contribuidores, idade |
| `releases.csv` | 350 repos · 43.709 releases (18.564 não-pré-release na janela; 4.579 pré-releases na janela, em 132 repositórios, entram só na variante C2 da RQ07) | data, pré-release, commits incluídos, lead time por release |
| `lead_time_repos.csv` | 350 repos | lead time (a) e (b) por repositório |
| `workflow_runs_repos.csv` | 350 repos | CFR (a), nº de episódios de falha e de episódios censurados |
| `episodios.csv` | 334 repos · 33.642 episódios | duração de cada episódio de falha de CI |
| `tags.csv` | 350 repos · 196.409 tags | tag, commit e data do commit (variante por tag da RQ07, fora do escopo; ver RQ07) |

### 2.5 Como lemos os gráficos

- **Gráfico de violino:** o contorno mostra *onde os repositórios se concentram* (quanto mais largo, mais repositórios naquele valor). Dentro dele, a caixa branca mostra mediana (traço colorido) e quartis (IQR), e os pontos são os repositórios individuais. Violinos substituem a média por algo mais honesto: as métricas são muito assimétricas, e um violino mostra a forma inteira da distribuição, inclusive se há dois "grupos" (bimodalidade).
- **Gráfico de bolhas:** cada bolha é um repositório. Posição = duas métricas; **tamanho e cor** carregam mais duas informações (ex.: estrelas e idade). Serve para ver relações e *confundidores* ao mesmo tempo.
- Escalas **logarítmicas** são usadas onde os valores variam por ordens de grandeza (cada marca é 10× a anterior).
- Todas as estatísticas descritivas são **mediana (IQR)**, como pedido no roteiro.

### 2.6 Validação manual (amostra-ouro)

Sorteamos 60 repositórios entre os 348 com pelo menos 5 releases avaliáveis e 5 releases de cada um (semente 42; 300 releases). Cada item recebeu três rótulos: tipo do projeto, se as releases são entregas reais ao usuário e se a release é corretiva. A rotulagem foi feita por **avaliação automatizada com um modelo de linguagem**, que leu a lista de commits de todas as releases e as notas da release ou a seção do CHANGELOG em 232 delas, sem ver a saída da heurística. A regra de decisão, a fonte e a justificativa de cada rótulo estão em `docs/protocolo_avaliacao_automatizada.md` e `validacao/justificativas_avaliacao_automatizada.csv`.

Resultado: 113 das 300 releases (37,7%) são corretivas; 58 dos 60 repositórios têm releases que são entregas reais (as exceções são um repositório de apps de exemplo e uma newsletter). Como há um único avaliador, **o kappa de Fleiss não pôde ser calculado** (ver Ameaças).

### 2.7 Testes estatísticos (simples e não paramétricos)

Wilcoxon (uma amostra ou pareado), Spearman (correlação por postos), Kruskal-Wallis com tamanho de efeito ε² = H/(n−1), correção de Holm para 20 testes na RQ06, kappa de Cohen ponderado (linear) na RQ07 e teste binomial para a proporção de mudança de categoria. Nível de significância: 5%.

---

## 3. Hipóteses

### 3.1 Hipóteses informais (registradas antes da coleta)

Antes de ver os dados, o grupo registrou expectativas para quatro questões (`docs/hipoteses_rq02_rq06.md` e `docs/hipoteses_rq03_rq04.md`). Comparadas com os resultados:

| RQ | O que esperávamos | O que encontramos |
|---|---|---|
| 02 | Lead time (b) de poucos dias a duas semanas; (a) bem maior, de duas a seis semanas, e (a) ≥ (b) em quase todos os repositórios | (b) com mediana de 11,7 dias, como esperado; (a) com 10,9 dias, muito abaixo do esperado, e (a) > (b) em só 63% dos repositórios |
| 03 | CFR (a) mediano de 10% a 25%, com cauda acima de 45%; CFR (b) menor, de 5% a 15%; correlação fraca entre os dois | CFR (a) de 5,9%, abaixo do esperado, com só 14 repositórios acima de 45%; CFR (b) de 20%, acima do esperado e inflado pela heurística (RQ03); correlação de fato fraca (ρ = 0,08; p = 0,16) |
| 04 | Recuperação mediana entre 1 h e 1 dia (faixa High), com cauda longa e menos de 20% de episódios censurados na maioria dos repositórios | Confirmado: mediana de 2,9 h, cauda até centenas de horas e mediana de 0% de censura por repositório |
| 06 | Efeitos pequenos a médios. Mais contribuidores e estrelas → mais releases e lead time menor, mas CFR (a) maior; projetos mais antigos → lead time maior, CFR menor e recuperação mais rápida; JavaScript, TypeScript, Go e Rust → mais releases e lead time menor; bibliotecas → CFR (b) maior | A idade tem efeito **grande** e na direção esperada para o lead time, mas não afeta CFR (a) nem recuperação. Mais contribuidores → lead time **maior**, ao contrário do esperado. Estrelas não afetam nada. Go tem o lead time **mais longo**. Bibliotecas têm CFR (b) **menor** que aplicações (17% contra 26%, sem significância) |

### 3.2 Hipóteses testadas

As hipóteses abaixo decorrem da literatura DORA e do senso comum de engenharia de software. **H0** é a hipótese nula (nada de interessante acontece); **H1** é a hipótese afirmativa (o que esperamos). Elas foram testadas contra os dados na seção 4.

| RQ | Hipótese nula (H0) | Hipótese afirmativa (H1) | Teste |
|---|---|---|---|
| **01** Frequência | A mediana de releases por semana é ≥ 1 (cadência semanal ou mais rápida). | A mediana é **< 1 por semana**: projetos open-source populares entregam menos de uma vez por semana. | Wilcoxon, 1 amostra |
| **02** Lead time | As variantes (a) e (b) têm o mesmo valor típico. | (a) é **maior** que (b): um commit antigo "esquecido" infla a variante por release. | Wilcoxon pareado |
| **03** CFR | O CFR de CI (a) e o de entrega (b) são iguais. | Diferem: falhar no pipeline (a) não é o mesmo que ter de corrigir uma release (b). Além disso, esperamos CFR (a) mediano ≤ 15% (Elite). | Wilcoxon pareado e 1 amostra |
| **04** Recuperação | A mediana do tempo de recuperação é ≥ 1 dia. | A mediana é **< 1 dia**: falhas de CI em projetos populares são resolvidas rápido. | Wilcoxon, 1 amostra |
| **05** Velocidade × estabilidade | ρ ≥ 0: mais deploys não se associam a menos falhas. | **ρ < 0**: repositórios que entregam mais vão melhor também na estabilidade (tese do DORA). | Spearman |
| **06** Características | A distribuição da métrica é a mesma em todos os grupos do fator. | Há diferença entre grupos (esperamos efeito de idade e popularidade). | Kruskal-Wallis + Holm + ε² |
| **07** Sensibilidade | No máximo 10% dos repositórios mudam de categoria quando a definição muda (classificação robusta). | **Mais de 10%** mudam (classificação sensível à definição). | Binomial + kappa ponderado |

---

## 4. Resultados por questão de pesquisa

### RQ01 — Frequência de deploy

| Métrica | n | Q1 | **Mediana** | Q3 |
|---|---:|---:|---:|---:|
| Releases por semana | 350 | 0,19 | **0,40** | 0,94 |

A mediana equivale a **uma release a cada ~2,5 semanas**. Pelos cortes DORA: 6 repositórios (2%) são Elite (≥ 7/semana), 22% são High, 46% Medium e 30% Low (< 1 por mês). Apenas 23% publicam ao menos uma release por semana.

**Teste:** Wilcoxon contra 1 release/semana → p = 5,5·10⁻¹⁵. **Rejeitamos H0**: a cadência típica é bem inferior a semanal.

![Violinos das quatro métricas DORA](./figs/fig01_violinos_dora.png)

**Leitura da figura 1 (primeiro painel):** o violino de frequência é largo na base (muitos repositórios entre 0,1 e 0,5 release/semana) e tem uma cauda fina que sobe até ~26/semana. A cauda é feita por poucos projetos que publicam quase automaticamente a cada mudança (ex.: `antiwork/gumroad`, ~1.240 releases no ano). A maioria dos pontos fica **abaixo** da linha "High ≥ 1".

### RQ02 — Lead time

| Variante | n | Q1 | **Mediana** | Q3 |
|---|---:|---:|---:|---:|
| (a) por release (dias) | 350 | 3,0 | **10,9** | 35,2 |
| (b) por commit (dias) | 350 | 2,5 | **11,7** | 36,6 |

- Correlação entre as variantes: ρ = 0,74 (relação forte, mas longe de idêntica).
- Em **63% dos repositórios** (a) > (b); a razão mediana (a)/(b) é 1,36. Wilcoxon pareado unilateral: p = 5·10⁻⁴ → **rejeitamos H0**.
- Pelos cortes DORA, só 13% dos repositórios têm lead time < 1 dia (Elite) e 29% têm ≥ 30 dias (Low).

![Bolhas: lead time (a) × (b)](./figs/fig02_bolhas_leadtime_a_b.png)

**Leitura da figura 2:** cada bolha é um repositório, e a diagonal tracejada marca "(a) = (b)". Os repositórios seguem a diagonal (por isso ρ = 0,74), mas **o enxame fica levemente acima dela** quando o lead time é grande: ali, um único commit antigo incluído na release puxa a variante (a) para cima, enquanto a mediana por commit (b) quase não se mexe. As bolhas grandes (repositórios com muitas releases) ficam perto da diagonal, porque a mediana de muitas releases suaviza esse efeito. A cor mostra um padrão adicional: **os repositórios mais novos (azul claro) estão no canto inferior esquerdo** (lead times de horas a poucos dias), e os mais antigos (azul escuro) no canto superior direito.

**Qualidade dos dados de lead time:** 2.436 de 18.493 releases (13%) não trazem commits novos em relação à anterior e foram excluídas do cálculo; 62 eram a primeira release do repositório; 7 tiveram erro 404 de `compare`. Também há **10.156 commits com lead time negativo** (0,36% de 2,8 milhões), concentrados em 25 repositórios: é sintoma de rebase, *squash* ou data de autor posterior à da release.

### RQ03 — Taxa de falha das mudanças (CFR)

| Variante | n | Q1 | **Mediana** | Q3 |
|---|---:|---:|---:|---:|
| (a) Proxy de CI | 350 | 2,5% | **5,9%** | 11,9% |
| (b) Proxy de entrega (patch ≤ 7 dias) | 344 | 8,7% | **20,0%** | 48,8% |

- **CFR (a):** 283 dos 350 repositórios (81%) ficam na faixa Elite (≤ 15%); só 14 passam de 45%. O teste de "mediana > 15%" não é rejeitado a favor de H1 (p ≈ 1): confirmamos que o valor típico está **abaixo** do corte Elite.
- **CFR (b):** 64 repositórios têm 0% e 15 passam de 90%, uma distribuição em "U" (ver figura 3, terceiro painel). Seis repositórios não puderam ser avaliados (menos de 5 releases avaliáveis ou tags fora do padrão SemVer).
- **Comparação pareada** (344 repositórios com as duas variantes): medianas de 5,7% (a) e 20,0% (b), Wilcoxon p = 2·10⁻²⁷. **Rejeitamos H0**: as variantes medem coisas diferentes.

**Por que divergem?** O CFR (a) mede *falha de pipeline*, que o desenvolvedor vê e corrige antes de publicar (um teste vermelho no PR não vira incidente). O CFR (b) tenta enxergar o que "escapou" para o usuário, mas é uma heurística grosseira: **mais da metade das releases (mediana de 55% por repositório) é seguida por outra release em ≤ 7 dias**, e em cerca de 75% desses casos a seguinte é só um *patch bump*. Projetos que publicam uma versão de patch a cada commit (ex.: `v0.2.11 → v0.2.12`) são marcados como "falhando" quase 100% do tempo sem que haja evidência de defeito.

**Validação contra a amostra-ouro.** Tratando como "corretiva" toda release que a regra usa para marcar uma falha (um *patch* da mesma linha publicado em ≤ 7 dias), a comparação com os 300 rótulos dá:

| VP | FP | FN | VN | Precisão | Recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 55 | 43 | 58 | 144 | 0,56 | 0,49 | **0,52** |

- **Falsos positivos (43):** são *patches* que trazem funcionalidades novas, comuns em projetos que só incrementam o *patch* (versões 0.x e monorepos com *changesets*). Como cada falso positivo faz uma release R contar como falha, **o CFR (b) desta seção está superestimado**: quase metade das "correções" que o alimentam não corrige nada.
- **Falsos negativos (58):** 45 são *patches* corretivos publicados mais de 7 dias depois da release anterior da linha (comuns em linhas LTS e de *backports*), e 13 não são *patch bumps* (ex.: uma *minor* só com correções). Esses casos não mudam o CFR (b), porque fora da janela de 7 dias nada conta como falha, mas pesam no *rework rate*.
- Sem o prazo de 7 dias, o critério de versão sozinho acerta mais: 100 das 171 releases que são *patch* da mesma linha são corretivas, e 100 das 113 corretivas são *patches*.

A comparação com as demais versões da heurística, que também olham as mensagens dos commits, está em `docs/heuristica_corretiva.md`.

### RQ04 — Tempo de recuperação

| Nível | n | Q1 | **Mediana** | Q3 |
|---|---:|---:|---:|---:|
| Por repositório (mediana dos episódios, horas) | 334 | 0,9 | **2,9** | 11,1 |
| Por episódio de falha (horas) | 33.517 | 0,7 | **2,1** | 7,8 |

- 86% dos repositórios têm mediana < 1 dia e 26% têm mediana < 1 hora. Wilcoxon (mediana < 24 h): p = 2·10⁻²⁸ → **rejeitamos H0**. Dezesseis repositórios não tiveram nenhum episódio de falha na janela e ficam sem valor.
- Por episódio: 32% se resolvem em < 1 h, 11% duram mais de 1 dia, e o percentil 90 é de 25 h.
- **Censura:** 125 dos 33.642 episódios (0,37%) não terminaram na janela; ficam fora da mediana, mas são contados. **Por repositório**, a proporção de episódios censurados tem mediana 0%: 254 dos 334 repositórios não têm nenhum, 90% ficam em até 3,2% e 15 passam de 10% (máximo de 75%, num repositório com poucos episódios). Nesses 15, a mediana de recuperação pode estar subestimada, porque os episódios mais longos são justamente os que não terminaram; no conjunto, o viés é desprezível.

![Violino do tempo de recuperação](./figs/fig06_violino_recuperacao.png)

**Leitura da figura 6:** o violino por episódio é **bimodal** (dois "calombos") na maioria das linguagens: um grupo de falhas que se resolve em ~1 h (reexecução, *flaky test*, correção trivial) e outro em ~15–20 h (correção que exige trabalho e costuma ficar para o dia seguinte). A mediana fica entre as duas bossas (~2 h), e é por isso que a mediana sozinha esconde essa estrutura. O segundo calombo é mais visível em Python e Rust. JavaScript tem menos episódios (383) e é o mais lento (mediana de 3,9 h, contra 1,6 h em TypeScript e Go). Atenção: poucos repositórios muito ativos contribuem com milhares de episódios, de modo que o gráfico é por episódio, não por repositório.

### RQ05 — Velocidade × estabilidade

| Frequência de deploy × … | n | Spearman ρ | p-valor |
|---|---:|---:|---:|
| CFR (a), proxy de CI | 350 | **+0,08** | 0,13 |
| CFR (b), proxy de entrega | 344 | **+0,54** | 4·10⁻²⁷ |

![Bolhas: frequência × CFR](./figs/fig05_bolhas_freq_cfr.png)

**Leitura da figura 5.** Cada bolha é um repositório; o tamanho é o número de estrelas e a cor é a idade (mais escuro = mais antigo).

- **Painel esquerdo (CFR de CI):** a nuvem é horizontal. Repositórios que entregam 0,1 ou 10 vezes por semana têm praticamente o mesmo CFR (quase todos abaixo de 20%). **Não há trade-off** entre velocidade e estabilidade, o que sustenta a afirmação do DORA. Mas **também não confirmamos H1** (ρ < 0): a relação é nula, não negativa. Rejeitamos H1.
- **Painel direito (CFR de entrega):** a nuvem sobe junto com a frequência (ρ = 0,54). A curva laranja tracejada, **1 − e^(−frequência)**, é o que esperaríamos *por pura aritmética*: se um repositório publica uma release por semana ao acaso, a chance de sair outra em ≤ 7 dias já é de 63%. Boa parte das bolhas acompanha essa curva, o que indica que **o ρ positivo é em grande parte efeito da definição, não de qualidade pior**. Medimos isso diretamente: a frequência correlaciona ρ = 0,75 com "a release foi seguida de qualquer outra em 7 dias", e a fração *dessas* que são patches cai levemente com a frequência (ρ = −0,17).
- **A idade é um confundidor.** A correlação do painel direito cai conforme o repositório envelhece: ρ = 0,65 (Q1 – mais novos), 0,65 (Q2), 0,38 (Q3) e **0,09, não significativo, nos mais antigos (Q4)**. Repositórios jovens publicam muito e em *patches* sucessivos; nos maduros, a heurística quase não distingue velocidade de falha. Já no CFR de CI, só o quartil mais antigo mostra correlação positiva fraca (ρ = 0,24; p = 0,02; n = 88); nos outros três ela é nula.
- Repositórios com ≥ 1 release/semana têm CFR (b) mediano de 58%, contra 18% nos mais lentos, mas, como vimos, essa diferença é largamente aritmética.
- **Recuperação:** a outra métrica de estabilidade aponta na direção do DORA. Quem entrega mais se recupera um pouco mais rápido (ρ = −0,16; p = 0,003; n = 334), uma relação fraca, mas no sentido esperado.

**Conclusão da RQ05:** os dados **não contradizem** o DORA (não há trade-off pelo critério de CI, e a recuperação melhora levemente com a frequência), mas **a resposta depende da métrica de falha**. Com o proxy de entrega, a evidência é contaminada pela própria definição.

### RQ06 — Características associadas ao desempenho

Quatro fatores (linguagem — 5 principais + "Outras"; quartis de estrelas, de contribuidores e de idade) × cinco métricas = 20 testes de Kruskal-Wallis, com correção de Holm. ε² é o tamanho de efeito (convenção usual: ~0,01 pequeno, ~0,06 médio, ≥ 0,14 grande).

| Fator | Métrica | n | ε² | p (Holm) | Conclusão |
|---|---|---:|---:|---:|---|
| **Idade** | Frequência de deploy | 350 | 0,094 | < 0,001 | **Significativo** (médio) |
| **Idade** | Lead time (a) | 350 | **0,203** | < 0,001 | **Significativo (grande)** |
| **Idade** | CFR (b) | 344 | **0,144** | < 0,001 | **Significativo (grande)** |
| **Contribuidores** | Lead time (a) | 350 | 0,103 | < 0,001 | **Significativo** (médio) |
| **Linguagem** | Lead time (a) | 350 | 0,098 | < 0,001 | **Significativo** (médio) |
| **Linguagem** | CFR (b) | 344 | 0,062 | 0,011 | **Significativo** (médio) |
| Idade | CFR (a) | 350 | 0,022 | 0,73 | Não significativo após Holm (bruto: p = 0,057) |
| Estrelas | todas as 5 métricas | 334–350 | 0,001–0,018 | 1,0 | **Nenhum efeito** |
| Linguagem / contribuidores / idade | CFR (a) e Recuperação | 334–350 | 0,004–0,022 | ≥ 0,73 | **Nenhum efeito**, agora com a amostra completa |

Os outros 14 testes têm p (Holm) ≥ 0,71. **Rejeitamos H0 em 6 dos 20 testes**; em todos os demais não há evidência.

![Violinos por idade](./figs/fig03_violinos_idade.png)

**Leitura da figura 3 (idade):** os três violinos contam a mesma história em ordem de idade. **Repositórios novos** (Q1) publicam mais (mediana 0,77 release/semana contra 0,27 nos mais antigos), têm lead time curto (2,6 dias contra 22–26 dias) e um CFR (b) muito alto e muito disperso (mediana 51%, violino largo de 0 a 100%). **Repositórios maduros** publicam menos, demoram mais para levar um commit à release (muitas vezes com *release branches* e ciclos de estabilização) e têm CFR (b) baixo (14–19%). É um padrão coerente de ciclo de vida: projetos jovens iteram rápido e em *patches* sucessivos; projetos maduros entregam em lotes maiores.

![Violinos por linguagem](figs/fig04_violinos_linguagem.png)

**Leitura da figura 4 (linguagem):** **Go** tem o lead time mais longo (mediana 34 dias) e **JavaScript** o mais curto (4,2 dias). O CFR (b) é mais alto em JavaScript (34%) e mais baixo em "Outras" (14%). Frequência de deploy não difere por linguagem (p bruto = 0,059; Holm = 0,73).

**Contribuidores:** quanto mais contribuidores, **maior** o lead time (mediana de 5,1 dias no quartil com menos contribuidores contra 24,5 dias no quartil com mais), possivelmente por mais revisão e coordenação, e também (efeito inverso) CFR (b) menor (29% → 17%, não significativo após Holm).

**Tipo do projeto (amostra-ouro, 60 repositórios).** O tipo só foi rotulado nos 60 repositórios da amostra-ouro (24 aplicações/serviços, 21 bibliotecas/frameworks, 7 ferramentas CLI e 8 outros), então é testado à parte, com Holm sobre os cinco testes. Só o lead time difere entre os tipos (ε² = 0,21; p Holm = 0,034): ferramentas CLI levam mediana de 53 dias, bibliotecas 14 dias e aplicações 8 dias. A frequência de deploy tem efeito bruto (p = 0,023), que não sobrevive à correção. Com grupos de 7 e 8 repositórios, esses resultados são indicativos.

**Popularidade (estrelas) não prevê nada.** Isso é um achado em si: ter muitas estrelas não implica melhor desempenho de entrega.

> As métricas de CI (CFR de CI e recuperação) não variam com nenhum dos quatro fatores. Com 334 a 350 repositórios, o teste tem poder para detectar efeitos médios; a ausência de efeito é, portanto, um resultado, e não falta de dados.

> Observação: idade, número de contribuidores e linguagem estão correlacionados entre si (projetos maduros têm mais contribuidores). Os testes são univariados, então **não separam o efeito de cada fator**; a idade é o candidato mais forte por ter os maiores ε².

### RQ07 — Sensibilidade da classificação DORA

Construímos quatro combinações de definições. Todas usam recuperação de CI (única definição disponível) e a classificação geral é a mediana (arredondada para baixo) das quatro notas, conforme o roteiro. Entram os repositórios com todas as notas da combinação: 334 em C1 e C3 (os 16 sem episódio de falha ficam fora) e 328 em C2 e C4 (que também exigem CFR (b)).

| Combinação | Unidade de deploy | Lead time | CFR |
|---|---|---|---|
| **C1** (referência) | release | (a) | (a) |
| **C2** | release + pré-release | (b) | (b) |
| **C3** | release | (b) | (a) — muda só o lead time |
| **C4** | release | (a) | (b) — muda só o CFR |

> A variante "tag" do roteiro (deploy = tag criada) ficou fora por decisão do grupo. As datas das tags foram coletadas (`tags.csv`), mas muitos projetos criam tags que não são entregas (marcos internos, tags de pacotes de monorepo, versões de teste), e separar umas das outras exigiria uma segunda heurística sem validação. As combinações acima variam a unidade de deploy pela inclusão de pré-releases (C2).

**Distribuição da categoria geral (repositórios):**

| Combinação | Low | Medium | High | Elite | n |
|---|---:|---:|---:|---:|---:|
| C1 | 15 | 167 | 131 | 21 | 334 |
| C2 | 20 | 191 | 113 | **4** | 328 |
| C3 | 13 | 170 | 127 | 24 | 334 |
| C4 | 16 | 211 | 98 | 3 | 328 |

**Concordância entre pares:**

| Par | % que mudou de categoria | κ ponderado | Leitura (Landis & Koch) | p (H0: mudança ≤ 10%) |
|---|---:|---:|---|---:|
| C1 × C3 (só lead time) | **14%** | **0,80** | substancial | 0,007 |
| C2 × C4 | 16% | 0,72 | substancial | 4·10⁻⁴ |
| C1 × C4 (só CFR) | 25% | 0,61 | substancial | 5·10⁻¹⁵ |
| C2 × C3 | 26% | 0,61 | substancial | 2·10⁻¹⁶ |
| C3 × C4 | 29% | 0,54 | moderada | 2·10⁻²² |
| **C1 × C2** (tudo muda) | **33%** | **0,47** | moderada | 4·10⁻²⁹ |

![Matriz de bolhas da sensibilidade](./figs/fig07_bolhas_sensibilidade.png)

**Leitura da figura 7:** cada bolha é um conjunto de repositórios cuja categoria na referência (eixo vertical) e na variante (eixo horizontal) são aquelas mostradas; o tamanho e o número dentro da bolha são a contagem. **Azul = classificação mantida** (sobre a diagonal), **laranja = mudou**.

- **C1 × C3** (troca só a variante de lead time): quase tudo na diagonal. O lead time é a definição **menos sensível**.
- **C1 × C4** (troca só o CFR): 52 repositórios "High" caem para "Medium" e **18 "Elite" caem para "High"**. A bolha laranja acima da diagonal mostra que o CFR (b) é sistematicamente mais severo do que o CFR (a).
- **C1 × C2**: só 4 repositórios são Elite em C2 (contra 21 em C1), e 33% mudam de categoria.

**Rejeitamos H0 em todos os pares**: a classificação é sensível à definição. A escolha do **proxy de falha** é a mais importante: ela sozinha desloca 25% dos repositórios, enquanto a variante de lead time desloca 14%.

**Robustez das conclusões anteriores:** as RQ 01, 02 e 04 (descrição de uma métrica) são estáveis; a **RQ05 não é robusta** (ρ = 0,08 vs. 0,54), e parte da RQ06 que usa CFR (b) deve ser lida com cautela.

---

## 5. Discussão: hipóteses × resultados

| RQ | Esperado (H1) | Encontrado | Surpresa? |
|---|---|---|---|
| 01 | Menos de 1 release/semana | Confirmado (mediana 0,40; p ≈ 10⁻¹⁵) | Não. A surpresa é a cauda: 6 projetos acima de 7/semana, quase automáticos. |
| 02 | (a) > (b) | Confirmado, mas o efeito é **pequeno** (razão 1,36) | Sim: esperávamos divergência maior; com a mediana, o "commit esquecido" pesa pouco. |
| 03 | CFR (a) ≠ (b); (a) ≤ 15% | Confirmado (6% vs 20%) | Moderada: o proxy de entrega é muito severo, e a causa está na heurística. |
| 04 | Recuperação < 1 dia | Confirmado (mediana 2,1–2,9 h) | A **bimodalidade** da distribuição não foi antecipada. |
| 05 | ρ < 0 | **Rejeitado**: ρ ≈ 0 (CI) e ρ > 0 (entrega) | **Sim.** O resultado positivo é em boa parte aritmética da definição. |
| 06 | Idade e popularidade importam | **Só a idade** (e contribuidores, linguagem e tipo do projeto em lead time); estrelas não | **Sim.** Popularidade não prevê desempenho. |
| 07 | Classificação sensível | Confirmado: 14–33% mudam | Menos do que o esperado para o lead time, mais do que o esperado para o CFR. |

**Mensagem principal:** o DORA ajuda a *comparar*, mas, com dados do GitHub, **o valor absoluto de uma métrica depende tanto da definição quanto do repositório**. As conclusões mais confiáveis são as que se repetem em mais de uma definição: (i) cadência de release lenta na maioria dos projetos, (ii) CI estável com recuperação rápida, e (iii) forte relação das métricas com a idade do projeto.

---

## 6. Ameaças à validade

**Construto (estamos medindo o que achamos?)**
- *Release ≠ deploy.* Bibliotecas e ferramentas publicam versões, mas quem faz deploy em produção são os usuários. A "frequência de deploy" é, na prática, frequência de **publicação**.
- *CFR (a) mede pipeline, não produção.* Uma falha de CI é muitas vezes corrigida antes de qualquer usuário ser afetado.
- *A heurística do CFR (b) não atinge o mínimo de validade.* Contra a amostra-ouro, a regra "patch ≤ 7 dias" tem precisão 0,56 e F1 0,52 (meta ≥ 0,70). Ela não olha as mensagens de commit (`fix`, `revert`, `hotfix`) e marca como falha projetos que fazem releases contínuas de *patch*. **Os valores de CFR (b) são um teto, não uma estimativa.**
- *A amostra-ouro tem um único avaliador automatizado.* Os rótulos vieram de um modelo de linguagem, não de três pessoas, então não há kappa de Fleiss para medir quanto o critério "release corretiva" é ambíguo. Os casos de fronteira são as releases mistas, com correções e funcionalidades na mesma versão.
- *Datas de commit.* `author.date` é distorcida por rebase/squash: há 10.156 commits com lead time negativo.

**Interna (há fatores não controlados?)**
- *Idade* é confundidor de várias análises: é correlacionada com frequência, lead time, CFR (b) e provavelmente com contribuidores. A RQ06 compara um fator de cada vez.
- 13% das releases (2.436) não trazem commits novos e foram excluídas do lead time, o que pode enviesar o resultado de projetos que republicam sem alteração.
- A variação de frequência entre projetos é de 270× (0,1 a 26 releases/semana); repositórios hiperativos geram milhares de episódios de CI e dominam a análise por episódio (fig. 6).

**Externa (vale além da amostra?)**
- Amostra de repositórios **muito populares** (≥ 1.915 estrelas), **open-source** e **com GitHub Actions**. Projetos corporativos fechados, com deploys de verdade em produção, podem ser muito diferentes.
- Os dados de CI cobrem os 350 repositórios, mas a recuperação existe só para os 334 que tiveram ao menos um episódio de falha; os 16 restantes ficam fora da RQ04 e da RQ07.
- Recorte único de 12 meses, que reflete um estado da evolução do ecossistema (grande presença de projetos de IA muito novos e ativos).

**De conclusão (a análise é adequada?)**
- Usamos testes não paramétricos e mediana/IQR; com 20 testes na RQ06 aplicamos Holm. Mesmo assim, p-valores minúsculos em n = 344 refletem poder estatístico, não necessariamente relevância prática: por isso reportamos ε² e ρ.
- Nos testes de grupo da RQ06, os menores grupos têm 25 repositórios (JavaScript). Um "não significativo" ali descarta efeitos médios ou grandes, mas não efeitos pequenos.
- Os episódios de falha são aninhados em repositórios (pseudorreplicação), o que torna o p-valor da análise por episódio otimista; por isso os testes foram feitos por repositório.
- O corte de lead time (mediana) limita a influência de *outliers* de até 4.000 dias, mas os cortes DORA usados são os fixos da disciplina (adaptados), não os de *clusters* anuais do relatório DORA.

---

## 7. Conclusão

1. **Quadro geral:** repositórios populares são, tipicamente, *Medium* DORA, com CI estável e recuperação rápida, mas com cadência de release lenta e lead times de dias a semanas.
2. **Velocidade × estabilidade:** não há evidência de trade-off medindo estabilidade pelo CI (ρ = 0,08). O sinal positivo (ρ = 0,54) do proxy de entrega é principalmente artefato da heurística.
3. **Quem vai melhor?** A idade do repositório é o fator mais associado (ε² até 0,20); linguagem e número de contribuidores importam para o lead time; **estrelas não importam**.
4. **Confiança nos números:** a mesma amostra produz de 14% a 33% de mudança de categoria conforme as definições operacionais. A escolha do proxy de falha pesa mais que a do lead time.

**Próximos passos sugeridos:** (i) avaliar contra a amostra-ouro as versões da heurística corretiva que usam mensagens de commit e recalcular o CFR (b) com a que tiver o melhor F1; (ii) usar modelos que controlem idade e linguagem juntas; (iii) testar o bônus de evolução trimestral (RQ08).

---

## Apêndice — Reprodução

Os dados de entrada estão em `src/data/` e são gerados pelo pipeline de coleta (`python src/pipeline.py`, descrito no README). A análise deste relatório roda sobre eles sem chamadas à API:

```bash
python docs/src/metricas.py src/data docs/resultados/metricas.csv > docs/resultados/metricas.txt
python docs/src/analise.py docs/resultados/metricas.csv > docs/resultados/analise.txt
python docs/src/graficos.py src/data docs/resultados/metricas_enriquecido.csv docs/figs > docs/resultados/graficos.txt
```

| Arquivo | Conteúdo |
|---|---|
| `docs/src/metricas.py` | calcula, por repositório, frequência, lead time, CFR (a/b), recuperação e classificações C1–C4 → `docs/resultados/metricas.csv` |
| `docs/src/analise.py` | RQ01–RQ07: estatísticas descritivas, testes de Wilcoxon, Spearman, Kruskal-Wallis (ε², Holm), kappa ponderado e testes binomiais → `analise.txt`, `rq06_testes.csv`, `metricas_enriquecido.csv` |
| `docs/src/graficos.py` | figuras de `docs/figs/` e números complementares da RQ04/RQ05 → `graficos.txt`, `rec_episodios_lang.csv`, `metricas_enriquecido_2.csv` |
| `docs/resultados/` | saídas acima; todo número do relatório sai de um desses arquivos |
| `validacao/amostra_ouro.csv`, `sorteio.json` | sorteio da amostra-ouro (`src/amostra_ouro.py`, semente 42) |
| `validacao/rotulos_avaliacao_automatizada.csv` | rótulos das 300 releases; justificativas em `justificativas_avaliacao_automatizada.csv` |
| `src/avaliar_heuristica.py` | precisão, recall e F1 de cada versão da heurística corretiva contra os rótulos |

Dependências: `pip install -r requirements.txt` (inclui scipy, matplotlib e seaborn para as figuras).

Parâmetros: janela de 01/10/2025 a 01/10/2026 (365 dias = 52,14 semanas); releases publicadas (`draft = false`, `prerelease = false`); CFR (b) exige ≥ 5 releases avaliáveis e ignora releases dos últimos 7 dias da janela; classificação DORA com os cortes fixos do roteiro (nota 4/3/2/1 por métrica, mediana arredondada para baixo).
