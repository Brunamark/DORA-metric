# Hipóteses informais: RQ 03 e RQ 04

Texto para a Introdução do artigo (Lab03S01, issue #3), escrito a partir do planejamento da issue, **antes** de analisar os dados da coleta. As faixas citadas são as da tabela de referência da RQ 07.

## RQ 03. Qual a taxa de falha das mudanças entregues por esses repositórios?

**Hipótese.** Esperamos um CFR (a), o proxy de CI, com mediana entre 10% e 25%, na fronteira entre as faixas *Elite* (≤ 15%) e *High* (≤ 30%), com cauda longa: uma parte dos repositórios deve passar de 45% e cair na faixa *Low*. Para o CFR (b), o proxy de entrega, esperamos uma mediana bem menor, entre 5% e 15%, o que poria a maioria dos repositórios na faixa *Elite*.

**Por quê.** O CFR (a) conta toda execução de workflow com falha no default branch, e boa parte dessas falhas não é uma mudança que quebrou o software: testes instáveis (*flaky*), falhas de infraestrutura do runner, dependências externas fora do ar e jobs não críticos, como lint, documentação e verificação de links. Repositórios com mais contribuidores e mais workflows rodam mais execuções por push e, por isso, devem acumular mais falhas. Já o CFR (b) só marca uma release como falha quando ela é seguida, em até 7 dias, por uma release corretiva. Esse evento é bem mais raro que uma execução vermelha, porque o próprio CI barra muitos defeitos antes da release.

**Por que as variantes divergem.** A variante (a) mede a saúde do *pipeline*; a variante (b) mede a qualidade do que foi entregue ao usuário. As duas podem andar em direções opostas. Um projeto com CI frequentemente vermelho pode ter releases estáveis, justamente porque o CI segura o problema antes da publicação, e um projeto com CI sempre verde pode publicar *patches* corretivos com frequência, porque os testes não cobrem o defeito. Esperamos, portanto, correlação fraca entre (a) e (b) e repositórios mudando de faixa DORA conforme a variante usada (RQ 07).

## RQ 04. Qual o tempo de recuperação após uma execução de CI/CD com falha?

**Hipótese.** Esperamos um tempo de recuperação mediano de poucas horas, entre 1 hora e 1 dia, o que poria a maior parte dos repositórios na faixa *High*. A distribuição deve ter cauda longa, com episódios de vários dias, e a proporção de episódios censurados deve ficar abaixo de 20% na maioria dos repositórios.

**Por quê.** Num projeto ativo, a correção típica de uma falha de CI é um novo push ou a reexecução do workflow, que costuma chegar em minutos ou horas. Episódios longos devem vir de workflows pouco disparados (cada push só aciona alguns deles), de falhas que começam perto do fim de semana e de falhas de infraestrutura externa, que dependem de terceiros. Os episódios censurados devem se concentrar em workflows abandonados ou quebrados no fim da janela, que ninguém corrigiu porque deixaram de importar.

**Viés esperado.** A listagem de runs mostra só a última tentativa de cada execução (`run_attempt`). Uma falha que passou na reexecução aparece como sucesso e não abre episódio. Isso tende a **subestimar** tanto o CFR (a) quanto o tempo de recuperação. Além disso, o episódio é medido por workflow: um sucesso de outro workflow não encerra a falha, o que evita encurtar episódios artificialmente em repositórios com muitos workflows.
