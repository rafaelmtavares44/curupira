# ADR 0012 — Revisão independente do lote, e o que ela mudou no pontuador

- **Status:** aceita
- **Data:** 2026-10-01
- **Contexto de:** Entrega 20
- **Relacionada a:** ADR 0005 D3, ADR 0009, ADR 0010, ADR 0011

## Contexto

A autocrítica da Entrega 19 dizia que as 36 tarefas do lote tinham **um autor
só**, e que os pontos cegos dele se repetiriam em todas. Dois controles
defeituosos, achados antes de escrever, provavam que os pontos cegos existiam.

A resposta foi uma **revisão independente**: três revisores, cada um com uma
lente, sem acesso ao raciocínio de quem escreveu — só aos arquivos.

| revisor | lente |
|---|---|
| linguista, nativo de pt-BR | naturalidade; a resposta certa é a única leitura de um nativo? a armadilha existe? |
| tradutor en↔pt | paridade: as duas versões pedem a mesma coisa, com o mesmo esforço? |
| crítico de benchmark | falso negativo, falso positivo, o controle controla? |

Eles acharam **um defeito de armadilha que não existia, quatro controles que
mudavam mais de um fator, uma assimetria sistêmica nas 40 tarefas em
português, e dois defeitos no pontuador** — nenhum deles visível para quem
escreveu.

## D1 — Pontuador: abster-se e agir na mesma resposta reprova

`pontuar_tool_call` removia as chamadas de abstenção antes de comparar, com a
justificativa de "perguntar e depois executar". Num harness de **turno único**,
as duas chamadas são simultâneas: o agente pergunta "confirma?" e transfere o
dinheiro antes de ouvir a resposta. Isso **passava**.

Agora reprova, na camada AST, com motivo próprio — em `tool_call` e em
`extraction`. Quando o harness multi-turno existir, a regra é revista junto.

## D2 — Pontuador: pergunta em prosa vai sempre ao juiz

No `clarify`, a prosa que casava a palavra-chave saía `ABSTEVE` — que **fica no
denominador e não é acerto** — e a que não casava saía `PENDENTE_DE_JUIZ`, fora
do denominador. **Acertar a palavra-chave piorava a nota.** O docstring antigo
chamava aquilo de *"acerto na camada VALIDADOR"*.

Duas saídas foram consideradas:

| | efeito |
|---|---|
| contar a prosa que casa como acerto (sugestão do revisor) | a lista de palavras-chave de cada idioma passa a **decidir a nota** — o viés que a ADR 0011 acabou de tirar do caminho da ferramenta |
| **toda prosa vai ao juiz** (escolhida) | nenhuma régua escrita à mão por idioma decide nada; as palavras-chave viram só uma pista no `motivo` |

A escolhida é a aplicação direta do princípio que o próprio pontuador declara:
*"nenhum deles chuta... o resíduo não é distribuído por igual entre os
idiomas"*. Para a fração que vai ao juiz não engordar, as tarefas de
esclarecimento instruem a perguntar pela ferramenta.

**Consequência a acompanhar:** o juiz ainda não existe. Até existir, pergunta
em prosa **sai do denominador**. Um agente que só pergunta em prosa contribui
pouco às famílias de esclarecimento, e o relatório mostra a fração.

## D3 — Matchers

- `one_of` ganha `case_sensitive: false`, como o `exact_str` já tinha. "maria
  lima" reprovava contra "Maria Lima".
- `contem_todos`, novo: texto livre que precisa mencionar termos, sem exigir a
  paráfrase. O texto do lembrete era não julgado, e `texto: "comprar pão"`
  passava num lembrete sobre convidar a Ana.

## D4 — Dataset

| achado | correção |
|---|---|
| **anáfora não existia**: com o Bruno citado por último, gênero e proximidade apontavam para ele | Bruno citado primeiro: gênero aponta para ele, proximidade para a Ana |
| **descrições pt-BR sem acento** nas 40 tarefas, só do lado português | acento em todas as livres; as `date-*` também tinham a mensagem do usuário sem acento |
| pedir confirmação antes de transferir reprovava como abstenção indevida | `system_prompt` de pedido já confirmado em toda tarefa que move dinheiro |
| `falta-argumento`: o agente não sabia que dia era hoje | âncora de data no `system_prompt`; controle refeito como par mínimo ("quarta da semana que vem") |
| `hora-12-24` fraca, e o controle exigia a mesma conversão da armadilha num lado só | armadilha "quinze pras três da tarde" (14:45); controle "três e quinze da tarde" (15:15), que é o erro típico da armadilha |
| `numero-por-extenso` sem nada de português no erro previsto | "dois mil e quinhentos **e cinquenta**": a cauda pode ser lida como centavos |
| `nomes-compostos`: as vírgulas resolviam sozinhas | sem vírgulas, nos dois lados |
| `referente-ambiguo`: controle mudava nome, gênero e preposição | mesma mensagem; só a agenda muda (um João só) |
| favorecido e servidor não eram julgados | `one_of` com a mesma lista nos dois lados |
| `ferramenta-em-ingles`: o controle não separava falso cognato de viés para `push` | terceira variante, `baixa os dados` → `pull` |

A convenção que saiu disso foi escrita no `tasks/README.md`: **o controle
difere da armadilha só no fator testado**, e o melhor desenho é a resposta do
controle ser o erro típico da armadilha.

Canários das 36 tarefas já publicadas foram **preservados**: o repositório é
público, e trocar o GUID apagaria a detecção de vazamento da versão que foi ao
ar.

## D5 — Onde discordei de um revisor

**`ferramenta-em-ingles` continua no Delta.** O revisor de paridade argumentou
que a família é "fácil por construção num lado só" e deveria sair do número da
manchete.

O argumento é sério, e a resposta é que ele vale igualmente para o par `money`,
que a ADR 0005 D3 manteve: `1,234.56` é fácil por construção em inglês, e
`1.234,56` é ambíguo só para quem carrega as duas convenções. O critério do
escopo é *"a mesma tarefa, a mesma ferramenta, a mesma dificuldade, rodada em
inglês e em português"* — e aqui a tarefa e a ferramenta são as mesmas; o que
muda é a língua do usuário, e a diferença de dificuldade **é** o efeito medido.
Tirar uma e manter a outra seria incoerente; tirar as duas seria redefinir o
Delta.

Fica registrado como o **segundo ponto mais atacável** do número, ao lado da D3
da ADR 0005, e a decisão volta à mesa se o primeiro piloto mostrar que essa
família sozinha move o Delta.

## Verificações novas

- **`test_oraculo_pelo_fio.py`**: um agente oráculo responde o gabarito em
  JSON-RPC, com não-ASCII escapado, pelo servidor MCP; a sessão vira
  `ExecucaoCrua`, é serializada como no `raw.jsonl`, relida e pontuada. Todas as
  46 tarefas passam. Mutação: o servidor lendo inteiro como float reprova as 8
  tarefas com inteiro no gabarito.
- **Ensaio de ponta a ponta** com o adaptador falso: `suite freeze` → `run` →
  `score` → `report` sobre as 46 tarefas, 92 execuções, zero erro de
  infraestrutura, **23 pares strict em 11 famílias** reconhecidos pelo Delta.

## Dívidas abertas

1. **Identificadores em português deixam o lado en-US bilíngue** (achado
   sistêmico do revisor de paridade). A direção líquida do efeito não é
   conhecida. Medir exige um braço de ablação com identificadores em inglês.
2. **O schema da tarefa está congelado sem decisão.** O hash é calculado sobre
   `model_dump(mode="json")`, que inclui campos com valor padrão: qualquer campo
   opcional novo muda o hash das tarefas congeladas, e a ADR 0008 proíbe
   recongelar. O gancho para o conserto é o `schema_version`, que toda tarefa já
   carrega. Precisa de decisão **antes** da próxima mudança de schema.
3. **O juiz não existe**, e a D2 manda toda prosa para ele.
4. **Revisão independente por modelo não é revisão humana.** Os três revisores
   foram subagentes: leitores diferentes de quem escreveu, mas não leitores
   humanos. A revisão humana das armadilhas continua sendo a defesa mais forte
   que o projeto não usou.

## Nota de método

Duas entregas atrás, a lição era *"antes de replicar um padrão, apresente o
padrão"*. Esta acrescenta a seguinte: **apresentar a quem não escreveu.** Três
leitores sem o contexto do autor acharam, em uma rodada, mais defeitos do que o
autor achou em três entregas de autocrítica.
