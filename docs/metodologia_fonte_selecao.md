# Rascunho — Metodologia: Fonte de dados e seleção

Texto para a subseção do artigo (template SBC), issue #8. Revisar e passar para o Overleaf. Os números entre colchetes saem de `src/data/funil.md` e de `src/data/repos_selecionados.csv` depois da coleta da amostra final.

---

**Fonte de dados e seleção.** Os dados vêm de repositórios públicos do GitHub, coletados por scripts próprios do grupo com as APIs REST e GraphQL do GitHub, sem bibliotecas de terceiros de acesso à API. A população-alvo são repositórios populares que usam CI/CD com GitHub Actions.

*Candidatos.* A busca de repositórios (`/search/repositories`) devolve no máximo 1.000 resultados por consulta. Por isso, ela foi fatiada em seis faixas de estrelas (1.000–2.000, 2.000–5.000, 5.000–10.000, 10.000–25.000, 25.000–60.000 e mais de 60.000). Em cada faixa, consideramos só repositórios com *push* depois do início da janela (`pushed:>=2025-10-01`): um repositório sem *push* na janela não pode ter execuções de CI por *push* nela, então o filtro reduz chamadas sem descartar candidatos válidos. A busca resultou em [5.347] candidatos únicos. Como a busca é ordenada por estrelas, em cada faixa só os 1.000 repositórios mais estrelados viram candidatos. Nas cinco faixas abaixo de 60.000 estrelas, o total de resultados passou desse teto: [16.595] na faixa de 1.000–2.000, [12.229] na de 2.000–5.000, [4.764] na de 5.000–10.000, [2.935] na de 10.000–25.000 e [1.097] na de 25.000–60.000. Dentro de cada faixa, portanto, a amostra pende para os repositórios mais populares. Isso é uma ameaça à validade externa, discutida na Seção [Ameaças].

*Ordem de avaliação.* Os candidatos foram embaralhados com semente fixa (`seed = 42`) e avaliados um a um até que [350] fossem aprovados. Fixamos o alvo em 350, acima do mínimo de 300 do estudo, como folga para repositórios que falhassem na coleta. A avaliação em ordem aleatória evita que a amostra se concentre nos repositórios mais populares, o que aconteceria se a lista fosse percorrida por número de estrelas. A semente fixa torna a seleção reproduzível. A amostra da Sprint 1 (100 repositórios) corresponde aos 100 primeiros aprovados nessa mesma ordem, e por isso está contida na amostra final.

*Critérios de inclusão.* Os filtros são aplicados nesta ordem, do mais barato ao mais caro em chamadas à API:
1. o repositório usa GitHub Actions (`/actions/workflows` com `total_count > 0`);
2. tem pelo menos 5 releases publicadas na janela (`draft = false` e `prerelease = false`);
3. tem pelo menos 50 *workflow runs* válidos na janela: execuções no *default branch*, disparadas por `push`, com `conclusion` igual a `success`, `failure`, `timed_out` ou `startup_failure`.

Os repositórios descartados e o motivo de cada descarte ficam registrados (`descartados.csv`).

*Funil.* A Tabela [X] mostra quantos repositórios restaram em cada etapa.

| Etapa | Restantes | Descartados | Motivo |
|---|---|---|---|
| Candidatos coletados na busca | [5.347] | | |
| Avaliados (ordem aleatória, seed fixa, até atingir o alvo) | [N] | [N] | não avaliados (alvo já atingido) |
| Usam GitHub Actions | [N] | [N] | sem workflows / erro de API |
| ≥ 5 releases publicadas na janela | [N] | [N] | releases insuficientes |
| ≥ 50 workflow runs válidos (push, default branch) | [N] | [N] | runs insuficientes |
| **Amostra final** | **[350]** | | |

O critério de releases foi o mais restritivo: [N%] dos repositórios avaliados com Actions foram descartados por ter menos de 5 releases na janela. Muitos projetos populares publicam versões só por tags ou por gerenciadores de pacotes, sem usar releases do GitHub. Isso é uma ameaça à validade externa, discutida na Seção [Ameaças].

*Metadados.* De cada repositório coletamos:
- estrelas (`stargazers_count`);
- linguagem principal (`language`);
- número de contribuidores, lido do número da última página de `/contributors?per_page=1&anon=true`;
- idade em dias, da criação do repositório até o fim da janela;
- *default branch*.

Esses metadados, com o tipo do projeto rotulado manualmente (Seção [Validação manual]), são os fatores da RQ 06. A amostra final tem [N] linguagens principais. A mediana de estrelas é [N] (IQR [N–N]), a de contribuidores é [N] (IQR [N–N]) e a de idade é [N] anos (IQR [N–N]).
