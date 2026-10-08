# Hipóteses informais: RQ 02 e RQ 06

Texto para a Introdução do artigo (Lab03S01, issue #2), escrito **antes** de ver os dados da coleta.

## RQ 02. Qual o tempo entre um commit e seu respectivo deploy?

**Hipótese.** Esperamos um lead time mediano de poucos dias a duas semanas na variante por commit (b) e bem maior, de duas a seis semanas, na variante por release (a). Com isso, a maior parte dos repositórios ficaria na faixa *High* (1 dia a 1 semana) pela variante (b) e na faixa *Medium* (1 semana a 30 dias) pela variante (a).

**Por quê.** Projetos open-source populares costumam publicar releases a cada uma a quatro semanas, e os commits se acumulam entre uma release e outra. Na variante (b), cada commit espera em média metade desse intervalo, então a mediana tende a ficar perto de meio ciclo de release. Na variante (a), o lead time de cada release é medido a partir do commit **mais antigo**, ou seja, cobre o ciclo inteiro ou mais.

**Por que as variantes divergem.** A variante (a) usa um único ponto extremo por release, o commit mais antigo; a variante (b) usa todos os commits e resume pela mediana. Um commit "esquecido" basta para inflar a variante (a): um branch longo mesclado tarde, um commit cuja data de autoria foi preservada num rebase ou num *squash merge*, ou um *backport*. A mediana da variante (b) quase não se move, porque esse commit é só um entre dezenas. Por exemplo, uma release com commits de 1, 2 e 3 dias e um commit de 90 dias tem lead time de 90 dias na variante (a) e de 2,5 dias na variante (b). Esperamos, portanto, (a) ≥ (b) em quase todos os repositórios, com a diferença maior nos projetos que usam branches de longa duração.

## RQ 06. Quais características dos repositórios estão associadas a um melhor desempenho DORA?

**Hipótese.** Esperamos diferenças estatisticamente significativas, mas de efeito pequeno a médio (|δ| < 0,474), entre os subgrupos dos fatores:

- **Contribuidores e popularidade:** repositórios nos quartis superiores devem ter maior frequência de deploy e menor lead time, porque costumam automatizar a publicação (bots de release, *semantic-release*, *release-please*). Por outro lado, devem ter CFR (a) mais alto, porque mais pessoas e mais pull requests geram mais execuções de CI e, com elas, mais falhas de pipeline.
- **Idade:** repositórios mais antigos devem ter ciclos de release mais longos e estáveis, com lead time maior, CFR menor e recuperação mais rápida, por terem processos mais maduros.
- **Linguagem:** ecossistemas com cultura de releases pequenas e frequentes, como JavaScript/TypeScript (npm), Go e Rust, devem ter maior frequência de deploy e menor lead time do que C/C++ e Java.
- **Tipo do projeto:** bibliotecas e frameworks devem publicar mais releases curtas, com muitos *patches*, e por isso ter CFR (b) mais alto. Aplicações e ferramentas CLI devem publicar com menos frequência e com mais mudanças por release.

**Por quê.** As práticas de entrega variam mais com a cultura do ecossistema e com o grau de automação do que com o tamanho do projeto. Como as métricas são *proxies* (release ≠ deploy, falha de CI ≠ falha em produção) e a amostra é heterogênea, esperamos que nenhum fator isolado explique grande parte da variação. Por isso, depois da correção de Holm, só alguns pares fator × métrica devem continuar significativos.
