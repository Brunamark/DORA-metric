# Heurística de release corretiva e CFR (b)

Issue #10 (Lab03S02). Código em `src/metricas.py` (funções puras), `src/corretivas.py` (etapa do pipeline) e `src/avaliar_heuristica.py` (validação contra a amostra-ouro).

## 1. O que a heurística decide

O CFR (b) é o proxy de **entrega**: uma release R **falha** se uma **release corretiva** que corrige R for publicada em até **7 dias** depois dela. A heurística decide, para cada release, se ela é corretiva, ou seja, se o objetivo principal dela é corrigir um defeito recente da release anterior.

- **CFR (b)** = releases que falharam ÷ releases avaliadas.
- **Censura:** uma release publicada nos **últimos 7 dias da janela** ainda não pode ser avaliada, porque não se sabe se haverá correção. Ela fica fora do denominador e é contada em `releases_censuradas`.
- **Prazo:** a corretiva publicada no 7º dia conta; no 8º, não. Uma release publicada exatamente 7 dias antes do fim da janela ainda é avaliada.
- **Unidade de deploy:** release publicada (`draft = false`, `prerelease = false`). As releases fora da janela servem só de contexto, como predecessoras.

## 2. Predecessora: decisão tomada com os dados

A heurística compara R com a release "anterior", e o CFR (b) olha a release "seguinte". Ordenar só pela data de publicação, que é a leitura literal do enunciado, quebra em dois casos comuns:

| Situação nos 100 repositórios da Sprint 1 | Repositórios | Exemplo |
|---|---|---|
| Linhas de versão paralelas (uma versão menor publicada depois de uma maior, com o mesmo prefixo) | 32 | ClickHouse publica `v25.8.10-lts` um dia depois de `v25.9.3-stable` |
| Monorepo, com vários pacotes e prefixos de tag | 19 | langchainjs tem 86 prefixos (`@langchain/core@0.3.5`, `@langchain/openai@0.4.1`, …) |
| Versão por calendário | 4 | `2025.10.1 → 2025.10.2` não significa correção |
| Tag que não segue `MAJOR.MINOR[.PATCH]` | 7 (26 tags de 10.364) | `cli-latest`, `release-2026-08-21` |

No pareamento cronológico, `v25.8.10` seria comparada com `v25.9.3`: a versão "regride" e o `compare` traz os commits de outra linha. Em 2.076 das 5.940 releases da janela (35%, em 30 repositórios), a predecessora muda conforme o pareamento.

**Decisão:** implementar as duas variantes e escolher a principal pelo F1 contra a amostra-ouro.

- **`linha`** (padrão): a predecessora de R é a **maior versão menor ou igual à de R, com o mesmo prefixo de tag**, entre as releases publicadas antes de R. Uma nova *minor* é comparada com o último patch da *minor* anterior (`25.10.1 → 25.9.4`). O primeiro pacote de um monorepo não tem predecessora. Uma tag sem versão usa a predecessora cronológica.
- **`cronologico`**: a release publicada imediatamente antes, como no lead time da Sprint 1.

Nas duas variantes, **R falha se alguma release corretiva cuja predecessora é R for publicada em até 7 dias.** No pareamento cronológico, isso equivale à leitura literal do enunciado: "a próxima release, se for corretiva".

## 3. Características de cada release (`releases_corretivas.csv`)

| Característica | Como é obtida |
|---|---|
| `tipo_mudanca` | `major`, `minor`, `patch`, `sufixo` (ex.: `+k3s1 → +k3s2`), `igual`, `regressao` ou vazio (sem versão, prefixos diferentes ou calendário), comparando com a predecessora |
| `n_commits`, `n_merges` | Commits de `compare/{predecessora}...{R}` e quantos são merges |
| `n_fix` | Títulos com `fix`, `hotfix` ou `revert` como palavra inteira (v1, igual ao enunciado: `fix:` e `fix(escopo):` casam; `prefix` e `fixture`, não) |
| `n_fix_amplo` | Também flexões e variantes (`fixes`, `fixed`, `bugfix`, `hot-fix`, `reverted`), sem contar merges |
| `n_fix_deps` | Títulos v1 que são atualização de dependência (`fix(deps): update dependency …`, `bump`) |
| `notas_mencionam_correcao` | Nome e notas da release com as palavras amplas (não entra em nenhum critério ainda; está disponível para o refinamento) |
| `patch_recente_7d` | A release é um patch publicado em até 7 dias depois de outra release da janela com o mesmo prefixo e o mesmo MAJOR.MINOR (regra do CFR (b) usada em `docs/src/metricas.py`, com a mesma leitura de versão) |

## 4. Versões da heurística

Cada versão é um par **pareamento × critério**. Os critérios usam lógica de três valores: um critério que precisa de uma informação ausente (ex.: versão de uma tag sem versão, ou commits de um `compare` com 404) fica **indeterminado**. No CFR (b), indeterminado conta como "não corretiva" e é contado em `releases_indeterminadas`.

| Critério | Regra | Por que testar |
|---|---|---|
| `semver_e_mensagem` (**v1**, padrão) | só o patch mudou **e** algum título tem fix/hotfix/revert | Regra do enunciado, versão "e" |
| `semver_ou_mensagem` | só o patch mudou **ou** algum título tem fix/hotfix/revert | Regra do enunciado, versão "ou": mais recall |
| `so_semver` | só o patch mudou | Isola o critério de versão |
| `so_mensagem` | algum título tem fix/hotfix/revert | Isola o critério de mensagem; não depende de SemVer |
| `semver_e_mensagem_sem_deps` | só o patch mudou **e** algum título de correção que não é atualização de dependência | Falso positivo previsto na issue: patch que só atualiza dependências |
| `semver_e_maioria_fix` | só o patch mudou **e** ≥ 50% dos commits (sem merges) são correção (palavras amplas) | Patch com uma correção e várias features não é "principalmente" corretivo |
| `relatorio_patch_7d` | `patch_recente_7d` | É a regra que gerou o CFR (b) do relatório: valida o número que está no texto. Não usa commits nem predecessora, então dá o mesmo resultado nos dois pareamentos |

## 5. Validação contra a amostra-ouro

1. O sorteio (`src/amostra_ouro.py`, semente 42) gerou `validacao/amostra_ouro.csv`: 300 releases, 5 de cada um de 60 repositórios (`validacao/sorteio.json`). A lista dos 60 está em `validacao/repos_amostra_ouro.csv`.
2. O integrante lê as notas da release e os commits do `compare` de cada item, e ficam em `validacao/rotulos_avaliacao_automatizada.csv` (colunas `repo`, `tag`, `corretiva` com sim/não/incerto). O `avaliar_heuristica.py` aceita esse arquivo, o `consenso.csv` da issue #9 (formato longo, com `dimensao`) e o formato largo (`full_name`, `tag_name`, `corretiva`).
3. **Só depois que a rotulagem terminar** (para os rótulos não serem influenciados pela heurística), rodar a etapa `corretivas` apenas nos 60 repositórios, gravando em `validacao/` para não sobrescrever os dados da amostra completa, e avaliar:
   ```bash
   python src/corretivas.py --inicio 2025-10-01 --fim 2026-10-01 --repos validacao/repos_amostra_ouro.csv --saida validacao
   python src/avaliar_heuristica.py --consenso validacao/rotulos_avaliacao_automatizada.csv --caracteristicas validacao/releases_corretivas.csv
   ```
4. `validacao/avaliacao_heuristica.csv` e `.md` trazem P, R e F1 de **todas** as 14 versões (2 pareamentos × 7 critérios), ordenadas por F1. `validacao/erros_heuristica.csv` lista os falsos positivos e falsos negativos de cada versão, com as características, e é o ponto de partida do refinamento.
5. Se a melhor versão tiver **F1 < 0,70**, refinar: analisar os erros, propor um critério novo em `metricas.CRITERIOS`, reavaliar e registrar a versão na tabela abaixo.

## 6. Resultados (preencher com `validacao/avaliacao_heuristica.md`)

| Versão | n | Precisão | Recall | F1 | Observação |
|---|---|---|---|---|---|
| relatorio_patch_7d (regra do relatório) | 300 | 0,56 | 0,49 | 0,52 | Calculada a partir de `src/data/releases.csv` (só usa tags e datas); o `avaliar_heuristica.py` reproduz o valor depois da etapa `corretivas` |
| linha/semver_e_mensagem (v1) | | | | | |
| … | | | | | |

**Versão final escolhida:** _(preencher)_ — justificativa: _(preencher)_

### Registro do refinamento

| Data | Versão | Mudança em relação à anterior | F1 | Motivo (erros analisados) |
|---|---|---|---|---|
| | v1 | Regra do enunciado | | |

## 7. Ameaças à validade ligadas à heurística

- **Construto:** "release corretiva" é inferida de números de versão e títulos de commit. Projetos que não seguem SemVer, ou que corrigem bugs em releases *minor*, ficam mal classificados; a amostra-ouro mede o tamanho desse erro.
- **Construto:** `fix:` do Conventional Commits também é usado em correções de documentação ou de testes, e bots usam `fix(deps):` em atualizações de dependência (por isso existe o critério `sem_deps`).
- **Interna:** o pareamento por linha supõe que prefixo + versão identificam a linha. Esquemas de tag que mudam ao longo do tempo (ex.: `v1.x` → `app-v2.x`) quebram a linha e deixam a release sem predecessora.
- **Interna:** um `compare` novo é limitado a 1.000 commits (`--max-paginas 10`). Releases truncadas ficam marcadas (`commits_truncados = sim`) e quase nunca são patches de correção.
- **Conclusão:** a amostra-ouro tem 300 releases (60 repositórios × 5). Se as corretivas forem raras, P/R/F1 terão intervalos de confiança largos; reportar n, VP, FP e FN junto com as taxas.
