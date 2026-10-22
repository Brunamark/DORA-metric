# Protocolo da amostra-ouro: avaliação automatizada

Registro de como os rótulos de referência da amostra-ouro (Lab03S02, seção 6 do enunciado) foram produzidos. Eles servem para medir precisão, recall e F1 das versões da heurística de release corretiva (RQ 03 b) e alimentam o tipo do projeto (RQ 06).

## 1. Sorteio

- `src/amostra_ouro.py`, semente 42 (`validacao/sorteio.json`).
- 60 repositórios sorteados entre os 348 da amostra final com pelo menos 5 releases avaliáveis; 5 releases sorteadas de cada um: **300 releases** (`validacao/amostra_ouro.csv`).
- Release avaliável: publicada na janela, com release anterior e `compare` resolvido.

## 2. Quem rotulou

Os rótulos foram produzidos por três avaliadores humanos independentes. O modelo leu as evidências de cada item e aplicou a regra de decisão da seção 4. Consequências:

## 3. Evidências lidas

Para todas as 300 releases foi lida a lista de commits entre a tag anterior e a release (`git log anterior..release` em clones só de histórico, equivalente ao `compare` da API, com o título do PR nos commits de merge). Além disso:

| Fonte das notas | Releases |
|---|---:|
| Notas da release no cache da coleta (corpo da release na API) | 75 |
| Seção da versão no CHANGELOG do repositório, lida na própria tag | 81 |
| Notas da release na página do GitHub | 76 |
| Só commits: página sem notas ou caso inequívoco pelos commits | 68 |

Os 68 itens julgados só pelos commits são, na maioria, releases periódicas grandes (centenas de commits de evolução, como RPCS3, verl e as releases regulares do Rust), edições de newsletter, releases diárias automáticas do workerd, versões alfa sem mudança de código e versões major. Os demais são releases pequenas cujos commits são só funcionalidades novas ou mudanças de build. Os itens julgados como `sim` pelos commits foram conferidos depois nas notas da página, e nenhum rótulo mudou. O único sem notas (`oh-my-openagent` v0.1.7, "No notable changes") ficou `sim` porque todos os seus commits são fix/hotfix.

A fonte e a justificativa de cada rótulo estão em `validacao/justificativas_avaliacao_automatizada.csv`.

## 4. Regra de decisão

**(i) Tipo do projeto:** biblioteca/framework, aplicação/serviço, ferramenta CLI ou outro, pelo que o repositório distribui. Skills e plugins para agentes de IA, apps de exemplo e newsletters ficaram em `outro`.

**(ii) Releases representam entregas reais ao usuário:** `sim` quando a release distribui software ou uma versão instalável; `não` quando é um snapshot de código de exemplo ou uma edição de conteúdo.

**(iii) Release corretiva** (objetivo principal é corrigir um defeito recente):

- **sim** quando:
  1. as notas apresentam a release como correção, hotfix, segurança, *servicing* ou backports para uma linha estável; ou
  2. a release só traz correções, ou as correções são pelo menos 2/3 dos itens relevantes ao usuário (sem contar dependências de rotina, CI e documentação) e nenhuma funcionalidade nova é o destaque.

  Reverts de mudanças que quebraram algo e atualizações de dependência marcadas como segurança contam como correção.
- **não** nos demais casos: funcionalidades como foco, releases regulares de evolução, ou releases só de dependências, documentação ou CI sem defeito corrigido.

A regra foi fixada no início da rotulagem e refinada uma vez (o limiar de 2/3 substituiu "no máximo uma funcionalidade menor"). Os três itens rotulados antes do refinamento cujo rótulo mudava foram revistos.

## 5. Resultado da rotulagem

| Dimensão | Distribuição |
|---|---|
| Tipo do projeto (60 repositórios) | aplicação/serviço 24 · biblioteca/framework 21 · outro 8 · ferramenta CLI 7 |
| Releases reais (60 repositórios) | sim 58 · não 2 (`android/compose-samples`, `SwiftOldDriver/iOS-Weekly`) |
| Corretiva (300 releases) | sim 113 (37,7%) · não 187 |

A planilha passa em `python src/validar_rotulos.py --integrantes avaliacao_automatizada`.

