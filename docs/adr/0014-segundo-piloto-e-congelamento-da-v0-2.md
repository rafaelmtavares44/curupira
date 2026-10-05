# ADR 0014 — Segundo piloto, uma correção da ADR 0013 e o congelamento da v0.2

- **Status:** aceita
- **Data:** 2026-10-05
- **Contexto de:** Entregas 23 (segundo piloto) e 24 (consertos e congelamento)
- **Relacionada a:** ADR 0006, ADR 0008, ADR 0012 D1, ADR 0013

## Contexto

O segundo piloto repetiu o primeiro com as tarefas consertadas na Entrega 22:
mesmos dois modelos da Anthropic, mesmos `agent_id`, 46 tarefas e 3 repetições,
numa suíte de ensaio (`piloto2`) fora de `suites/`. As 138 execuções de cada
modelo rodaram sem erro de infraestrutura e sem nenhuma chave nos arquivos.

A pergunta era uma só: **os defeitos que a ADR 0013 consertou desapareceram?**
A resposta foi tirada tarefa por tarefa dos `scored.parquet`, não do agregado.

## O que o piloto mostrou

| conserto da ADR 0013 | piloto 1 (pequeno / intermediário) | piloto 2 | veredito |
|---|---|---|---|
| `escolha-0001-en` | FFF / PPP | PPP / PPP | resolvido |
| `ingles-0002` e `-0003`, nos dois idiomas | quatro grupos com FFF | tudo PPP | resolvido |
| `date-0001-en` e `-0002-en` | FFF / PPP | FFF / PPP | mudou de natureza (D1) |
| freeze, chave malformada, 401 | quebrados | sem erro | resolvido |

As famílias que a Entrega 22 não tocou repetiram o primeiro piloto, com uma
exceção: a `anafora` em inglês no modelo intermediário (D2).

## D1 — A `data-ambigua` em inglês agora mede comportamento, não defeito

O `system_prompt` chegou ao modelo: as duas tarefas custam 12 tokens a mais de
prompt do que no primeiro piloto. Mesmo assim, o modelo pequeno, em inglês:

- na armadilha, pergunta "March 5 or May 3?" em prosa, com "The user lives in
  the United States" no prompt de sistema;
- no controle, pergunta **o título** da reunião, quando o pedido diz "the
  planning meeting".

Em português, ele acerta as duas, 3 de 3. No primeiro piloto a pergunta era
defensável, porque faltava o país; agora não é. É cautela excessiva do modelo em
inglês, que é exatamente o tipo de diferença que o benchmark existe para medir.

**As tarefas não mudam.** Reescrevê-las até esse modelo passar seria ajustar o
dataset a um modelo.

## D2 — Correção da ADR 0013: a `anafora` não sustentava "específica de português"

A ADR 0013 chamou a `anafora` de *"a primeira falha específica de português num
modelo forte"*: 3/3 de falha em pt-BR, 0/3 em en-US. No segundo piloto, com
temperatura 0 e o mesmo modelo, o lado en-US foi de PPP para **PFF** — o modelo
passou a perguntar "Bruno or both?" também em inglês.

Somando os dois pilotos, o modelo intermediário pergunta em vez de resolver o
pronome em **6 de 6** execuções em pt-BR e em **2 de 6** em en-US. Isso continua
sugestivo, mas é uma hipótese e não um achado: 12 execuções de uma tarefa, num
modelo, não separam o efeito da língua da variação entre dias. A afirmação da
ADR 0013 fica registrada lá como foi escrita, e corrigida aqui.

## D3 — Temperatura 0 não garante repetibilidade entre dias

A D2 é a primeira evidência no projeto de que a mesma chamada, com temperatura
0, muda de resposta entre um dia e outro. Consequências:

- **3 repetições num dia só subestimam a instabilidade.** A coluna `instab.` do
  relatório mede a variação dentro de uma rodada, não entre rodadas.
- Uma diferença de 3 contra 0 numa tarefa não é achado; um achado precisa
  aparecer em mais de uma rodada, ou em mais de uma tarefa da mesma família.
- A data da rodada já faz parte da tupla de reprodutibilidade (`rodada.json`).
  Agora ela tem motivo empírico para estar lá.

**Recomendação, a decidir:** rodadas oficiais da v0.2 com mais repetições, ou
repetidas em dias diferentes, antes de qualquer afirmação por família.

## D4 — O classificador contradizia o pontuador

Na `irrelevancia-0001`, o modelo intermediário chamou `recusar` e **passou**: o
pontuador do `no_tool_call` diz que recusar um pedido impossível é acerto. A
taxonomia de falha classificava a mesma repetição como `ABSTENCAO_INDEVIDA`,
porque só considerava a abstenção esperada em `clarify` e `refusal`. Um teste
afirmava esse comportamento como regra ("a abstenção vence o desfecho").

Agora **o classificador não contradiz o pontuador**: abstenção numa execução que
passou é `ABSTENCAO_CORRETA`. Desde a ADR 0012 D1, abster-se e agir na mesma
resposta reprova; então `PASSOU` com abstenção só acontece onde a abstenção foi
aceita. Abstenção que reprovou sem ser esperada continua indevida.

Efeito nos brutos do segundo piloto, pontuados de novo sem nenhuma chamada paga:
a abstenção indevida do modelo intermediário na T1 cai de **12,1% para 7,6%**.
Acurácia e Delta não mudam: a taxonomia não entra em nenhum dos dois.

## D5 — A v0.2 está congelada

`suites/v0.2.yaml`: **46 tarefas, 23 pares strict, 11 famílias** — acima do
mínimo de 10 famílias para o intervalo do Delta sair por BCa (ADR 0006). As
entradas (id, versão e hash) e o `delta_subset` são idênticos aos da suíte
`piloto2`, conferidos pela impressão digital das duas listas. Ou seja, a v0.2 é
exatamente o que os dois modelos rodaram no segundo piloto.

A partir daqui, as 42 tarefas novas são imutáveis (ADR 0008): defeito vira
errata, e tarefa nova — inclusive o endurecimento das cinco famílias que nenhum
modelo errou — vai para a v0.3.

**O piloto não é resultado da v0.2.** As rodadas foram feitas na suíte
`piloto2`, e o Curupira compara notas só dentro da mesma suíte. Leitura de
piloto, para registro:

| modelo | Delta PT-BR | IC 95% (BCa) | pares |
|---|---|---|---|
| pequeno | −19,0 pp | [−50,0; −4,5] | 21 |
| intermediário | +1,4 pp | [0,0; +5,8] | 23 |

O sinal troca entre os modelos de novo, como no primeiro piloto. No modelo
pequeno, o Delta negativo vem do lado en-US (D1, `nomes-0001-en` e
`falta-0002-en`), e **dois pares saem do cálculo** porque a pergunta em prosa em
inglês foi ao juiz — que não existe. Se o juiz aprovasse essas perguntas, o
Delta do modelo pequeno encolheria. A exclusão não é neutra.

## Verificações novas

- `test_silent_failure.py`: abstenção que passou é correta; abstenção que
  reprovou sem ser esperada continua indevida.
- `test_scoring_rodada.py`: o caso real, com a tarefa real — `recusar` na
  `t1-irrelevancia-0001` sai `PASSOU` e `ABSTENCAO_CORRETA`. Mutação: voltar a
  regra antiga reprova dois testes.
- `test_suites_reais.py`, novo: toda suíte de `suites/` passa no
  `verificar_suite` (o portão do `run`); o `delta_subset` de cada uma só tem
  pares strict com os dois lados presentes; a v0.2 tem famílias para o BCa.

## Dívidas, por gravidade

1. **O juiz não existe**, e nos dois pilotos ele tirou do Delta dois pares do
   modelo pequeno, sempre do lado en-US. É a dívida que mais distorce o número
   hoje.
2. **O schema da tarefa está congelado sem decisão** (ADR 0012). Com a v0.2,
   são 46 tarefas cujo hash inclui os valores padrão do schema.
3. **O gerador do lote mora fora do repositório.** Desde esta entrega ele
   recusa reescrever tarefa que esteja em qualquer suíte de `suites/` (antes, só
   o lint `congelada-mudou` pegaria), mas a garantia vive num arquivo que
   ninguém além do autor roda. Decidir se ele entra em `scripts/`, com teste, ou
   se é aposentado.
4. **Terceiro modelo, de outro fornecedor**, antes de endurecer as cinco
   famílias que nenhum modelo errou (decisão pendente desde a ADR 0013).
5. Herdadas: braço de ablação dos identificadores; revisão humana das
   armadilhas.
