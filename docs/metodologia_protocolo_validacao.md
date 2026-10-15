# Metodologia: protocolo de validação manual

Texto da subseção para a seção de Metodologia do artigo (Lab03S02). Os trechos `<preencher>` saem de `validacao/sorteio.json`, `validacao/kappa.md` e `validacao/consenso.csv`, depois que os três integrantes rotularem a amostra. O texto das subseções de seleção/funil e de cálculo das métricas vem das outras duas issues e deve ser integrado ao template SBC (Overleaf) na ordem: seleção e funil, definições operacionais, protocolo de validação.

## Protocolo de validação manual

As métricas deste estudo dependem de heurísticas automáticas, em particular a que identifica uma release corretiva (CFR b). Para medir o quanto elas erram, construímos uma **amostra-ouro**, rotulada por pessoas, e a usamos como referência.

**Sorteio.** Dos `<preencher: N>` repositórios da amostra final, `<preencher: M>` tinham ao menos cinco releases avaliáveis, isto é, publicadas na janela de observação, com uma release anterior publicada (que serve de base para a lista de commits) e com a comparação entre as duas resolvida pela API. Sorteamos 60 repositórios entre eles, com semente fixa (`random_state = 42`) e, de cada um, cinco releases avaliáveis, também com semente fixa, o que totaliza 300 releases. O código ordena repositórios e releases antes de sortear, de modo que o sorteio é reproduzível independentemente da ordem dos arquivos de entrada.

**Rotulagem independente.** Cada um dos três integrantes preencheu a própria planilha, sem consultar os demais e sem ver a saída da heurística; as planilhas, idênticas na origem, traziam apenas links diretos para o repositório, para a release e para a lista de commits entre as duas releases. Cada integrante registrou (i) o **tipo do projeto** (biblioteca/framework, aplicação/serviço, ferramenta CLI ou outro); (ii) se as releases do repositório **representam entregas reais** ao usuário (sim, não ou incerto), e (iii) se cada uma das cinco releases sorteadas é **corretiva** (sim ou não), a partir das *release notes* e dos commits. Um script conferiu, antes de qualquer cálculo, que as planilhas estavam completas e usavam somente os valores permitidos, e que os julgamentos do repositório (i e ii) eram os mesmos nas cinco linhas de cada um.

**Concordância.** Medimos a concordância entre os três avaliadores com o **kappa de Fleiss**, que corrige a concordância esperada por acaso, em cada dimensão: 60 itens (repositórios) em (i) e (ii), e 300 itens (releases) em (iii). Interpretamos os valores pela escala de Landis e Koch (1977). Obtivemos κ = `<preencher>` para o tipo do projeto, κ = `<preencher>` para releases como entregas reais e κ = `<preencher>` para release corretiva (Tabela `<preencher>`). Um kappa baixo indica que o próprio critério é ambíguo; discutimos esse resultado na seção de ameaças à validade.

**Consenso.** O rótulo de referência de cada item é o da **maioria simples** dos três avaliadores (decisão automática). Os casos sem maioria (1-1-1) foram decididos em reunião, com a evidência aberta diante dos três (`<preencher: n>` de `<preencher: total>` itens). O protocolo de desempate está registrado no repositório (`docs/protocolo_consenso.md`), assim como a decisão de cada caso (`validacao/decisoes_reuniao.csv`).

**Avaliação da heurística.** Comparamos a heurística de release corretiva com o rótulo de consenso da dimensão (iii) e calculamos **precisão** (das releases que a heurística marcou como corretivas, quantas realmente eram), **recall** (das realmente corretivas, quantas ela encontrou) e **F1** (média harmônica das duas). Quando o F1 ficou abaixo de 0,70, refinamos a heurística e reavaliamos; cada versão testada e o F1 obtido por ela estão na Tabela `<preencher>`. O rótulo de tipo do projeto alimenta a RQ 06 como fator de comparação.

**Limites do protocolo.** A amostra-ouro tem 60 repositórios, e os três avaliadores são também os autores do estudo; ambos os fatores limitam a generalização e são retomados nas ameaças à validade.

**Referência.** Landis, J. R.; Koch, G. G. The measurement of observer agreement for categorical data. *Biometrics*, 1977.
