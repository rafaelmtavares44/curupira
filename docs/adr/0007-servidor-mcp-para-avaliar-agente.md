# ADR 0007 — Servidor MCP: o Curupira passa a medir agente

- **Status:** aceita
- **Data:** 2026-09-16
- **Contexto de:** Entrega 13
- **Relacionada a:** ADR 0002 (adaptadores próprios), ADR 0005 D3 (assimetria declarada)

## Contexto

O escopo do projeto diz, com todas as letras:

> *"NÃO é leaderboard de modelo, e sim de AGENTE: modelo + framework + prompt +
> tools. Trocar CrewAI por LangGraph muda a nota, e essa informação é o produto."*

Depois de doze entregas, o `curupira run` falava **direto com a API do
provedor**. Havia uma opção `--framework`, e ela era apenas um rótulo no
registro da rodada: não mudava nada na execução. O que o Curupira media era o
modelo, não o agente.

A distância entre a promessa e o código apareceu quando a pergunta foi feita do
jeito mais simples possível: *"como eu e os usuários vamos usar isso?"*.

## O que já existia lá fora

**AgentBeats** (arXiv, 2026) enfrenta exatamente este problema e o resolve sem
integração ponto a ponto:

> *"reduz o custo de integração de N × M combinações agente-benchmark para N + M
> integrações em nível de protocolo"*

> *"o agente avaliado pode residir em um repositório separado e ser desenvolvido
> por uma parte independente"*

Eles usam dois protocolos existentes: **MCP** para as ferramentas e **A2A** para
a tarefa. O A2A deixou de ser projeto de um fornecedor: foi doado à Linux
Foundation, chegou à v1.0 e passou de 150 organizações com uso em produção.

Inventar protocolo aqui seria erro.

## D1 — O Curupira é um servidor MCP

**A direção se inverte.** Em vez de o Curupira chamar o agente, o agente chama o
Curupira. Ele conecta num servidor MCP, vê as ferramentas que a tarefa declara,
e faz o que a mensagem do usuário pede. O Curupira observa as chamadas.

Cinco razões para isso cair sob medida neste projeto, e nenhuma é genérica:

1. **O dataset já está no formato.** Cada tarefa declara `context.tools` com
   `parameters` em JSON Schema, que é exatamente o `inputSchema` do MCP. Zero
   conversão, e existe um teste que cobra essa igualdade campo a campo.
2. **É o que medimos.** A métrica é *qual ferramenta, com quais argumentos*. Um
   servidor MCP vê isso nativamente, sem parsear resposta de modelo.
3. **O pipeline não mudou.** O servidor grava a mesma `ExecucaoCrua`; `score` e
   `report` funcionam sem uma linha de alteração — família, Delta e falha
   silenciosa incluídos.
4. **A T1 fica trivial.** "Tool descrita em inglês com usuário falando
   português" vira servir a descrição em inglês.
5. **Nenhum adaptador novo, nunca mais.** Framework que surgir, se fala MCP,
   roda aqui.

## D2 — Escrito à mão, e o motivo não é tamanho

A primeira versão desta decisão dizia que o protocolo "são duas mensagens
JSON-RPC". **Estava errado.** A revisão 2026-07-28 exige `resultType` em todo
resultado, `_meta` validado em toda requisição com `protocolVersion` e
`clientCapabilities` obrigatórios, códigos de erro próprios, negociação de
versão e regras de segurança sobre JSON Schema.

O motivo verdadeiro é outro, e é específico do Curupira. A especificação manda:

> *"Servers MUST validate all tool inputs"*

Um servidor MCP normal valida os argumentos contra o `inputSchema` e **rejeita**
o que não bate. **Aqui o argumento errado é a medição.** Um agente que manda
`valor_centavos: 123456000` onde o gabarito é `123456` acabou de errar por mil
vezes, em silêncio, do jeito exato que a tarefa foi desenhada para capturar. Um
SDK que rejeitasse antes de chegar ao nosso código apagaria o dado.

Somos um servidor **anômalo**: queremos registrar chamadas erradas, não executar
chamadas certas. Daí a regra que governa o módulo:

> **GRAVA PRIMEIRO, VALIDA DEPOIS.**

Duas consequências, as duas testadas:

- **Ferramenta inexistente é gravada** e depois recusada com o erro que a
  especificação manda. Alucinação de ferramenta é comportamento do agente.
- **Erro de envelope não é gravado.** `_meta` ausente, versão incompatível, JSON
  quebrado: isso é integração malfeita de quem avalia, e penalizaria o agente por
  um erro que não cometeu.

Isto é o eco da ADR 0002, que recusou o LiteLLM no núcleo — e aquela decisão
envelheceu bem. A diferença é que lá o argumento era supply chain, e aqui é
comportamento: nenhum SDK de servidor é desenhado para preservar o erro.

## D3 — O leaderboard tem duas colunas que nunca se misturam

O agente roda na máquina de quem avalia. **Quem avalia pode trapacear**: editar a
resposta, ter visto as tarefas antes, rodar cem vezes e submeter a melhor. E,
mesmo sem má-fé, vários campos da tupla de reprodutibilidade deixam de ser
observáveis — `model`, `framework`, `temperature`, `prompt_template_id` são
**auto-declarados**, porque um servidor MCP não enxerga nenhum deles.

Quase todo leaderboard de agente finge que esse problema não existe. O Curupira
o exibe:

| selo | o que significa |
|---|---|
| **auto-reportado** | quem avalia rodou e submeteu. O Curupira confere formato, hashes da suíte, canários e a tupla — e **nada mais** |
| **verificado** | o Curupira executou, em CI, contra a suíte held-out que ninguém viu |

Um número auto-reportado não é lixo; ele só não é a mesma coisa que um número
verificado, e o leitor merece saber qual está lendo. O `adapter_version` do
resultado carrega `mcp/2026-07-28`, então rodadas por MCP e por API direta nunca
são confundidas — **elas não são comparáveis**, porque o objeto medido é outro.

Os canários já no dataset permitem conferir contaminação de um resultado
auto-reportado meses depois.

## D4 — A abstenção já era observável, e o A2A encolheu

A primeira versão desta ADR previa o A2A como camada obrigatória, porque o MCP é
stateless por especificação — *"MCP has no protocol-level session"* — e portanto
não sabe dizer quando o agente terminou.

**Metade dessa preocupação estava errada**, e a descoberta veio de olhar o
dataset: toda tarefa já declara duas ferramentas padrão, escritas na Parte A
justamente para *"tornar a abstenção detectável por AST, sem juiz e sem léxico de
hedge"*:

```yaml
- name: pedir_esclarecimento
- name: recusar
```

Um agente que quer perguntar **chama uma ferramenta**. Uma chamada é exatamente
o que este servidor vê. Logo:

| `expect.kind` | mecanismo | precisa de A2A? |
|---|---|---|
| `tool_call` | `tools/call` observado | não |
| `clarify` | chamada a `pedir_esclarecimento` | **não** |
| `refusal` | chamada a `recusar` | **não** |
| `extraction` | argumentos da chamada | não |
| `sequence` | ordem das chamadas | não |
| `no_tool_call` | **ausência** de chamada | ainda em aberto |

Sobrou **um** caso. Distinguir "não chamou nada" de "ainda não chamou" é o único
lugar onde o MCP realmente não basta.

O desenho do dataset antecipou o problema um ano antes de o protocolo entrar na
conversa. Isso é validação forte do modelo de dados da Parte A.

## Consequências

1. `src/curupira/mcp/` com `protocolo`, `servidor` e `rodada`. Transporte stdio
   apenas; o Streamable HTTP traz SSE, autorização e sessões de stream, e nada
   disso é necessário para medir tool calling.
2. `curupira serve --suite v0.1 --tarefa <id>` sobe o servidor. **O stdout
   pertence ao protocolo**; toda mensagem para humano sai no stderr.
3. A sessão termina quando o stdin fecha, e o resultado grava
   `finish_reason: stdin_fechado`. É provisório e legível no dado: rodadas
   antigas não serão confundidas com as que vierem depois da Entrega 14.
4. A resposta da ferramenta é `{"status": "ok"}`, **sem palavra em idioma
   nenhum**. Uma confirmação em português apareceria só na versão PT-BR do par e
   parte do Delta estaria medindo a nossa própria resposta — a mesma armadilha
   que a ADR 0005 D3 registrou na notação numérica, aqui eliminada de vez. Há um
   teste que recusa palavra dos dois idiomas no conteúdo.

## O que fica para a Entrega 14

**A camada de tarefa, e só para o `no_tool_call`.** Dois caminhos:

- **A2A completo** — padrão, e o `TASK_STATE_*` dá terminação de graça. Custo:
  uma superfície de protocolo inteira para resolver um caso.
- **Subprocesso** — o Curupira executa o agente como comando e o fim do processo
  delimita a tarefa. Simples, e já é o que o `serve` faz na prática.

Com a D4, o A2A perdeu a maior parte da justificativa. A decisão agora exige
medir quanto custa cada um, e não é mais óbvia na direção que eu supunha.

## Riscos declarados

**O agente pode não usar as nossas ferramentas.** Se ele já tem outras plugadas,
pode resolver a tarefa por fora e nunca tocar no nosso MCP. Não é trapaça, é
ambiente diferente — mas torna a comparação injusta se não for controlado, e hoje
não é.

**A especificação se move.** Implementar à mão significa acompanhá-la. A versão
está declarada numa constante e um cliente que peça outra recebe
`UnsupportedProtocolVersion` em vez de uma conversa que quase funciona.

**O `_meta` é auto-reportado.** A própria especificação avisa que `clientInfo` e
`serverInfo` *"are self-reported by the sender and are not verified"*. Não os
usamos para decidir nada.

## Referências

- [AgentBeats: Agentifying Agent Assessment for Openness, Standardization, and Reproducibility](https://arxiv.org/html/2606.13608v1)
- [MCP Specification 2026-07-28 — Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [MCP Specification 2026-07-28 — Overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/index.md)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [Linux Foundation — A2A Protocol](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year)
