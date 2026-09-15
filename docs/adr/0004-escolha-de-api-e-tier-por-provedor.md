# ADR 0004 — Escolha de API e de tier por provedor

- **Status:** aceita
- **Data:** 2026-09-15
- **Contexto de:** Entrega 8 (adaptador da OpenAI)
- **Relacionada a:** ADR 0002 (camada de adaptadores)

## Contexto

Ao escrever o adaptador da OpenAI, dois fatos apareceram e nenhum deles é
detalhe de implementação — os dois mudam o que o benchmark mede.

### Fato 1: os dois provedores têm duas APIs vigentes

Em setembro de 2026, OpenAI e Google fizeram o mesmo movimento, com a mesma
redação:

| Provedor | API antiga | API nova | O que a doc diz |
|---|---|---|---|
| OpenAI | Chat Completions | Responses | *"While Chat Completions remains supported, Responses is recommended for all new projects."* |
| Google | `generateContent` | Interactions (GA jun/2026) | *"While `generateContent` remains fully supported, we recommend the Interactions API for all new development."* |

Nenhum dos dois anunciou data de fim para a API antiga.

### Fato 2: o free tier do Gemini não garante não-treinamento

A documentação de faturamento do Gemini diz que o **paid tier** garante que
*"your prompts and responses are not used to improve Google products"*. Para o
free tier essa garantia **não existe**.

## Decisão

### D1 — OpenAI: Chat Completions, não Responses

O motivo é do Curupira, não da OpenAI.

O formato Chat Completions virou padrão de fato: Groq, Together, DeepSeek,
vLLM local e vários outros expõem endpoint compatível. O Curupira é um
leaderboard de **agente** (modelo + framework + prompt + ferramentas), e um
adaptador que fala esse formato multiplica os agentes mensuráveis sem uma linha
a mais de código. A Responses é proprietária e não serve para mais ninguém.

**Contra-argumento reconhecido:** se a OpenAI puser recurso agêntico novo
apenas na Responses, mediremos o agente com uma mão amarrada.

**Gatilho de revisão:** quando um recurso relevante para as trilhas T1 ou T6
existir só na Responses, ou quando a OpenAI anunciar data de fim para a Chat
Completions. A ADR 0002 já desenhou o contrato de adaptador de modo que a
troca seja um arquivo.

### D2 — Google: decisão adiada, e declarada como adiada

O argumento de alcance que decide D1 **não se aplica ao Google**: o
`generateContent` não é padrão de fato de ninguém. Sem ele, não há razão para
nascer legado — mas também não há informação suficiente para escrever o
adaptador da Interactions API sem inventar assinatura, o que este projeto
proíbe. Faltam, na documentação que conseguimos ler:

- onde ficam `seed` e o limite de tokens de saída;
- a estrutura exata dos `execution_steps` na resposta;
- se há contagem de tokens (sem ela, o custo por acerto do relatório fica cego).

Os dois stubs de `adapters/google.py` permanecem abertos, com esta ADR como
motivo registrado. `tests/stubs_pendentes.txt` aponta para cá.

### D3 — Nenhum provedor roda o benchmark em tier sem garantia de não-treinamento

Rodar o Curupira no free tier do Gemini significaria entregar as tarefas de
avaliação a um pipeline que pode usá-las em treino. É **exatamente** o
vazamento que os `canary_guid` existem para detectar, causado por nós, de
propósito, na primeira rodada.

O dano seria assimétrico: o provedor contaminado ganharia vantagem estrutural
no nosso próprio leaderboard, e o canário acenderia meses depois apontando para
a nossa metodologia.

Isto vale como **critério de aceitação de qualquer provedor futuro**, não como
observação sobre o Google: um provedor entra no leaderboard quando existe um
tier cujos termos garantam que prompt e resposta não alimentam treino, e a
rodada usa esse tier.

Detalhe operacional registrado: basta **um** projeto com faturamento habilitado
para que os prompts do AI Studio caiam sob os termos de serviço pago.

## Consequências

1. O adaptador da OpenAI serve, de graça, para todo provedor compatível com
   Chat Completions. Isso é alcance que não estava no roadmap.
2. `strict` **não** é enviado nas ferramentas. Com `strict: true` a OpenAI
   força a saída a casar com o schema — ou seja, conserta o erro que o
   benchmark existe para medir.
3. `RespostaCrua` ganhou `provider_fingerprint`. A `seed` da OpenAI é
   *best-effort*, e o `system_fingerprint` é a única evidência verificável de
   que o backend não mudou entre duas rodadas.
4. **Assimetria de medição declarada:** `function.arguments` chega como string
   JSON na OpenAI e como objeto já decodificado na Anthropic. O `raw_arguments`
   da OpenAI é o literal do modelo; o da Anthropic é reconstruído por nós. Isso
   não afeta o Delta PT-BR (que usa só passou/não passou), mas **afeta qualquer
   comparação de modo de erro entre provedores**, e o relatório precisa dizer
   isso quando cruzar `silent_failure_if` de provedores diferentes.
5. O leaderboard da v0.1 sai com Anthropic e OpenAI mais os compatíveis. O
   Google entra quando D2 for resolvida.

## Alternativas rejeitadas

- **Responses API agora.** Alcance de um provedor só, em troca de recursos que
  a v0.1 não usa.
- **Escrever o adaptador do Google deduzindo a API pela SDK.** Viola a regra de
  não inventar assinatura. Uma dedução errada num adaptador não falha alto: ela
  produz número, e número errado num benchmark é pior que benchmark quebrado.
- **Rodar o Google no free tier "só para o piloto".** O vazamento é
  irreversível: uma vez que a tarefa entrou no pipeline de treino, nenhuma
  rodada posterior desfaz a contaminação, e o dataset público inteiro fica
  suspeito.
