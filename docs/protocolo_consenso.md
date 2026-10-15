# Protocolo de consenso da amostra-ouro

Registro de como os três rótulos independentes viram um rótulo de referência (Lab03S02). O consenso da dimensão `corretiva` é a entrada da avaliação de precisão, recall e F1 da heurística de release corretiva (RQ 03 b); `tipo_projeto` alimenta a RQ 06.

## Antes do consenso

1. Cada integrante preenche a **própria** planilha (`validacao/rotulos_<integrante>.csv`) **sem consultar os demais e sem ver a saída da heurística**.
2. O script `src/validar_rotulos.py` confere se cada planilha está completa e só usa valores permitidos. O kappa e o consenso só são calculados depois de as três passarem.

## Regra automática: maioria simples

O rótulo mais votado vence quando recebe **mais da metade dos votos**. Com três avaliadores:

| Votos | Resultado | `decidido_em` |
|---|---|---|
| 3-0 | rótulo unânime | `maioria` |
| 2-1 | rótulo dos dois | `maioria` |
| 1-1-1 | sem maioria | `reuniao` |

A dimensão `corretiva` tem só duas categorias (sim, não), então nunca cai em 1-1-1. Os empates só acontecem em `tipo_projeto` (4 categorias) e `releases_reais` (3 categorias).

Os itens são: um por repositório em `tipo_projeto` e `releases_reais`; um por release sorteada em `corretiva`.

## Casos 1-1-1: decisão em reunião

1. O script lista cada caso em `validacao/decisoes_reuniao.csv`, com os votos de cada avaliador. Enquanto houver caso sem decisão, `consenso.csv` fica com `rotulo_consenso` vazio nesses itens e o script termina com erro.
2. Os três se reúnem e abrem juntos o repositório, a release e a lista de commits (links na planilha). Cada um justifica o próprio voto.
3. O grupo busca decisão **por discussão**, com base na evidência (release notes, commits, README), e não por insistência.
4. Se não houver acordo, vale a **maioria simples dos três votos depois da discussão**.
5. Se ainda assim ninguém tiver maioria, o rótulo é o **menos comprometedor** da dimensão: `incerto` em `releases_reais` e `outro` em `tipo_projeto`. O grupo não força um rótulo que ninguém sustenta.
6. A decisão vai na coluna `rotulo_reuniao`, e o motivo em `observacao` (uma linha). Depois, rodar `python src/consenso.py --integrantes <nomes>` de novo grava a decisão no `consenso.csv` com `decidido_em = reuniao`.
7. As decisões já preenchidas são preservadas quando o script roda de novo.

## Regras de registro

- `decidido_em` é sempre `maioria` ou `reuniao`; nenhuma linha fica sem rótulo no consenso final.
- Os rótulos individuais **não são alterados** depois do cálculo do kappa: o kappa mede a concordância **antes** do consenso. Corrigir um erro de digitação é permitido (e deve ser feito antes de calcular o kappa).
- O consenso final e `decisoes_reuniao.csv` são commitados, para que o grupo replicador consiga conferir como cada caso foi decidido.
- O resultado é citado na seção de Metodologia (Protocolo de validação manual) com o nº de itens decididos por maioria e em reunião.
