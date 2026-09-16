# ADR 0005 — O que a primeira rodada real ensinou

- **Status:** aceita
- **Data:** 2026-09-16
- **Contexto de:** Entrega 9 (primeira rodada paga)
- **Relacionada a:** ADR 0004, pendências P1 e P2 do escopo

## Contexto

Em 16/09/2026 o Curupira falou com modelos de verdade pela primeira vez: dois
agentes, `claude-haiku-4-5-20251001` e `claude-sonnet-4-5-20250929`, três
repetições, suíte v0.1 (4 tarefas, 2 pares strict). Vinte e oito chamadas no
total. Zero erro de infraestrutura.

Os dois Deltas vieram assim:

| agente | acurácia | falha silenc. | abst. indev. | instab. | Delta PT-BR |
|---|---|---|---|---|---|
| haiku-45-k3 | 91,7% | 0% | 8,3% | 25% | **+16,7%** |
| sonnet-45-k3 | 50,0% | 50% | 0% | 0% | **−100,0%** |

**Os dois Deltas são artefatos, e apontam em direções opostas.** Nenhum dos dois
mediu o que o Curupira existe para medir. Esta ADR registra as quatro decisões
que essa descoberta obriga.

## D1 — O limiar do `fuzzy_name` reprovava comportamento defensável

### O que aconteceu

O Sonnet acertou **os seis valores** em centavos — `123456` e `123400`, o
gabarito exato, nas três repetições e nos dois idiomas. A armadilha do separador
decimal, que é o objeto da tarefa, ele resolveu perfeitamente.

Reprovou no **favorecido**. A mensagem em inglês é `pay 1,234 to supplier Silva`
e ele mandou `favorecido: "supplier Silva"` onde o gabarito dizia `"Silva"`. O
`fuzzy_name` com `threshold: 0.9` cortou.

Em português (`pro fornecedor Silva`) o mesmo modelo mandou `"Silva"`. A
diferença de comportamento entre os idiomas é real; a **reprovação** é escolha
nossa.

### A dívida que cobrou

Desde a Entrega 2 estava anotado: *"o limiar 0.9 do `fuzzy_name` é hipótese, não
medição"*. Ela cobrou na primeira rodada real, e cobrou caro: produziu um Delta
de −100% que não tem nada a ver com idioma.

### Decisão

`"supplier Silva"` **é uma resposta aceitável**. Se a ferramenta cria uma
transferência para um favorecido, incluir o rótulo que o usuário usou é
comportamento razoável, não erro.

Isso vira `expect.accept` explícito — o mecanismo já existe no schema desde a
Parte B e foi desenhado exatamente para isto. Não baixamos o limiar: trocar um
número arbitrário por outro não resolve nada, e **esconde a decisão dentro de um
parâmetro em vez de declará-la no dataset**.

O `rationale` de cada alternativa passa a carregar o porquê, em texto, auditável
por humano.

## D2 — Regra de autoria: uma variável por tarefa

### O princípio

**Cada tarefa mede uma coisa.** Nada que não seja o objeto do teste pode ser
fonte de reprovação.

A tarefa do par `money-0002` existe para medir o separador decimal. O nome do
favorecido é ruído experimental — e foi o ruído que decidiu a nota, nas doze
execuções do Sonnet.

### O que isso obriga

Ao autorar, para cada argumento que não é o objeto da tarefa, responder: *este
campo pode reprovar um agente que resolveu a armadilha?* Se puder, ou ele entra
em `accept` com as variações defensáveis, ou sai da mensagem.

Esta é a regra mais valiosa que a rodada produziu, porque vai reger as ~60
tarefas do piloto — e cada tarefa mal desenhada teria sido replicada trinta
vezes.

## D3 — A assimetria de ambiguidade dentro de um par `strict`

### O que o Haiku revelou

Na tarefa `money-0002` em português, o Haiku **não errou: perguntou**. E a
pergunta trazia a interpretação correta:

> *"O valor de 1.234 é em reais? Você quer dizer R$ 1.234,00 (mil duzentos e
> trinta e quatro reais)?"*

Em inglês, o mesmo modelo executou direto. A causa é a notação:

- `1,234` em inglês é **inequívoco** — vírgula é separador de milhar, e pronto.
- `1.234` em português é mil duzentos e trinta e quatro, mas o ponto é separador
  **decimal** na convenção anglófona. Para um modelo que carrega as duas, o
  texto brasileiro é genuinamente ambíguo.

Contraste com o par `money-0001`, cuja mensagem é `1.234,56`: essa forma **só
existe** na convenção brasileira, não é ambígua, e o Haiku acertou nos dois
idiomas.

### Decisão

**As duas versões de um par `strict` não têm, e não podem ter, a mesma
ambiguidade intrínseca.** A ambiguidade é propriedade da convenção numérica de
cada língua, e a convenção numérica é parte do objeto de estudo — o projeto mede
degradação quando "o usuário fala português **e o mundo ao redor é brasileiro:
formatos**".

Então: o par continua `strict`, e o `parity_notes` passa a **declarar a
assimetria** em vez de afirmar equivalência que não existe. Dizer "apenas o
idioma muda" era verdade e era insuficiente.

Quem ler o Delta precisa saber que parte dele vem da notação. Esconder isso
seria vender como efeito de idioma algo que é efeito de convenção numérica.

## D4 — O leaderboard só aceita identificador de modelo com data

`GET /v1/models` da Anthropic devolve dois tipos de identificador:

| tipo | exemplo | comportamento |
|---|---|---|
| com data | `claude-haiku-4-5-20251001` | fixo |
| sem data | `claude-sonnet-5` | **alias móvel** |

Um alias aponta para a versão mais recente e muda sozinho. Registrar um alias na
tupla de reprodutibilidade faria a tupla mentir exatamente onde ela promete não
mentir: a mesma rodada, meses depois, falaria com outro modelo e nada acusaria.

**Decisão:** o campo `model` do registro de rodada só aceita identificador com
data. Um alias é erro de uso, não conveniência.

*Pendência:* a validação ainda não está no código. Enquanto não estiver, é
disciplina — e disciplina não é portão.

## Consequências

1. `task_version` sobe de 1 para 2 nos quatro arquivos do par. As tarefas nunca
   são editadas em silêncio.
2. **A suíte v0.1 deixa de ser rodável.** Ela congela `task_version: 1` e os
   hashes correspondentes, e esses arquivos já não existem. Como a v0.1 nunca
   foi publicada e só rodou como piloto, ela é recongelada.
3. As rodadas de 16/09 ficam amarradas às tarefas versão 1. Continuam válidas
   como registro histórico, e **não são comparáveis** com rodadas futuras.

### Tensão de design exposta, e ainda não resolvida

A promessa era: *"a v0.1 continua rodável para sempre"*. Mas o dataset guarda
**um arquivo por tarefa**, então corrigir uma tarefa apaga a versão que a suíte
congelada aponta. As duas coisas não são compatíveis como estão.

Três saídas possíveis, nenhuma escolhida ainda:

- guardar as versões antigas lado a lado (`t2-money-0002.pt-BR.v1.yaml`);
- reconstruir a versão antiga a partir do histórico do git no momento da rodada;
- assumir que uma suíte congelada é **imutável de verdade** — corrigir uma
  tarefa cria tarefa nova com id novo, e a antiga entra na errata.

**Isso precisa estar decidido antes da v0.1 ir a público**, porque depois disso
alguém de fora vai tentar reproduzir uma rodada e não vai conseguir.

## O que esta ADR NÃO decide

**A categoria "abstenção cautelosa" não entra agora.** O Haiku pediu confirmação
de algo que sabia, o que é diferente da abstenção de quem não faz ideia — mas
isso apareceu em **uma** tarefa, de **um** modelo, com instabilidade de 25%.

Criar categoria de desfecho a partir disso seria formalizar ruído. Fica como
hipótese a testar quando o dataset tiver tamanho para responder.

## Nota de método

Esta ADR existe porque a rodada veio **antes** da autoria em escala. As quatro
decisões acima nasceram de vinte e oito chamadas e alguns centavos. Tomadas
depois de sessenta tarefas escritas, cada uma teria custado a reescrita das
sessenta.
