# ADR 0013 — O que o primeiro piloto pago ensinou

- **Status:** aceita. A leitura da `anafora` ("específica de português") foi
  corrigida pela ADR 0014 D2: o segundo piloto não a sustentou.
- **Data:** 2026-10-01
- **Contexto de:** Entregas 21 (piloto) e 22 (consertos)
- **Relacionada a:** ADR 0005, ADR 0008, ADR 0010, ADR 0012

## Contexto

O primeiro piloto rodou as 46 tarefas livres (23 pares strict, 11 famílias) em
dois modelos da Anthropic — um pequeno e um intermediário — com 3 repetições,
numa suíte de ensaio congelada fora de `suites/`. O objetivo não era o número:
era descobrir o que o dataset e o harness fazem de errado quando um agente de
verdade, e não o adaptador falso, está do outro lado.

Ele achou **três defeitos de tarefa** e **três defeitos do Curupira**. Nenhum
apareceu nos mais de mil testes nem no ensaio com o adaptador falso: o falso não
pergunta, não hesita e não cola chave errada.

## O que o piloto mediu (leitura de piloto, não resultado)

- **O sinal do Delta troca entre os dois modelos.** É o que a tese do projeto
  prevê — o agente importa, não só a língua —, mas com 11 famílias e 3
  repetições não sustenta nenhuma afirmação além de "vale medir".
- **A primeira falha específica de português num modelo forte:** na `anafora`,
  o modelo intermediário perguntou "para o Bruno, a Ana, ou ambos?" nas três
  repetições em pt-BR, e resolveu o pronome em en-US.
- **A armadilha `nomes-compostos` pegou o modelo pequeno em inglês**, separando
  "João Pedro" em dois convites. Em português, não.
- **Cinco famílias ninguém errou:** o falso cognato `puxa/pusha`, "quinze pras",
  "e cinquenta", o separador decimal e a irrelevância. Endurecê-las agora seria
  ajustar o dataset a dois modelos de um fornecedor só (ver Próximos passos).
- **Duas tarefas de esclarecimento foram ao juiz em en-US** (pergunta em prosa,
  apesar da instrução), e o Delta saiu com 21 pares em vez de 23. A fração que
  vai ao juiz é assimétrica entre os idiomas — mais um motivo para o juiz
  existir antes da v0.2 virar número publicado.

## D1 — Três tarefas reprovavam o agente cuidadoso

O padrão dos três: **a tarefa deixava uma lacuna que não era o objeto dela**, e
perguntar pela lacuna era uso defensável da abstenção — que o gabarito
reprovava.

| tarefa | o que o agente fez | conserto |
|---|---|---|
| `data-ambigua` (en-US) | perguntou se `03/05` era março ou maio | `system_prompt` diz onde o usuário mora: Brasil / Estados Unidos. Em inglês, sem país, a ambiguidade é real (EUA × Reino Unido) |
| `data-ambigua` (controle) | perguntou o horário da reunião | a descrição diz "reunião **de dia inteiro**" |
| `escolha-de-ferramenta` | perguntou quando lembrar ("amanhã" não tinha campo) | a descrição diz "o momento de lembrar vai no próprio texto" |
| `ferramenta-em-ingles` (controles) | os dois modelos nomearam o servidor de jeitos que a lista do `one_of` não previa | `server` vira `enum: [backup, staging]` |

No `ferramenta-em-ingles`, o servidor do segundo controle passou de "produção"
para **staging**: com `enum` em inglês, "produção" exigiria traduzir, e o
controle deixaria de diferir da armadilha só no fator testado. "Backup" e
"staging" são ditos sem tradução no jargão dev brasileiro.

As 14 tarefas alteradas sobem para `task_version: 2`. Elas eram livres (nenhuma
está em `suites/`), mas **já tinham sido rodadas**: o resultado do piloto fica
amarrado à v1, e o hash recusa pontuar o bruto velho contra a tarefa nova.
Canários preservados.

A convenção que sai disso foi escrita no `tasks/README.md`: *a ferramenta não
deixa lacuna que a tarefa não quer testar.*

## D2 — `suite freeze` lia as suítes congeladas do lugar errado

O lint do congelamento procurava as suítes congeladas na pasta de **destino**.
Congelar a suíte de ensaio numa pasta descartável fazia as tarefas `money-*`,
congeladas na v0.1 antes de várias convenções, serem tratadas como livres — e
reprovadas por regras que a ADR 0010 diz não valerem para elas.

Agora `--destino` (onde gravar) e `--congeladas` (o que já foi congelado) são
opções separadas. O padrão de `--congeladas` é a pasta `suites/` **irmã da
pasta de tarefas** — não do diretório corrente, que no PowerShell é onde o
usuário estiver.

## D3 — Chave malformada é recusada antes da primeira chamada

Na primeira tentativa do piloto, a variável de ambiente recebeu o texto de um
comando colado por engano, com um caractere não-ASCII. O erro apareceu como
`'ascii' codec can't encode character`, sem pista nenhuma.

Duas barreiras, as duas antes de qualquer pedido de rede:

1. `carregar_chave` recusa valor vazio, não-ASCII, não imprimível ou com espaço
   (`chave_bem_formada`). A mensagem **não cita o valor**, e o valor recusado
   não entra no registro de segredos.
2. A CLI confere o prefixo do provedor (`sk-ant-`, `sk-`). É uma verificação de
   forma, não de validade: ela pega a colagem errada, não a chave revogada.

## D4 — A rodada para no primeiro 401/403

Com a chave ainda inválida, a segunda tentativa disparou as 138 chamadas e
recebeu 138 vezes o mesmo 401. Com uma chave válida mas sem permissão — ou com
limite de gasto —, o mesmo defeito queimaria tempo e orçamento.

`401` e `403` interrompem a rodada (`RodadaInterrompida`). O que já estava em
voo termina — no máximo um lote de `--concorrencia` pedidos —, nada novo sai, e
o bruto parcial fica para inspeção. `429`, `5xx` e falha sem status continuam
virando linha de erro, como antes: são transitórios, e a rodada segue.

A interrupção é um `SinalDeRecusa` compartilhado entre as corrotinas, e não uma
varredura do bruto: a decisão nasce do `status` do `ErroDoProvedor`, que é
estruturado, e não de texto.

**O bruto parcial não se pontua.** A primeira versão desta decisão dizia isso na
mensagem de erro, e nada impedia: o `score` pontuaria o bruto parcial e
produziria um número sobre um subconjunto de tarefas que ninguém escolheu. A
autocrítica achou antes da entrega. Agora o `run` cria a marca `INCOMPLETA`
antes da primeira chamada e só a apaga quando a última linha foi gravada sem
recusa; o `score` recusa diretório com a marca. Isso cobre também o erro de
segurança no meio da rodada e o Ctrl+C. O caminho MCP (`curupira serve`) não
cria a marca: cada sessão grava uma execução completa. Exigir o `rodada.json`
foi a primeira ideia, e foi descartada justamente por quebrar o `serve`.

## D5 — Comentário que promete o que o código não faz (sexta ocorrência)

Os testes da CLI diziam rodar "sem rede". Eles batiam em `api.anthropic.com`
com uma chave falsa, e passavam porque a resposta era um 401 — que, depois da
D4, mudaria o comportamento deles. Agora uma `RedeFalsa` autouse intercepta o
`httpx` em todo `test_cli.py`, e os testes de fail-fast contam os pedidos que
ela recebeu.

É a sexta vez no projeto que um comentário ou docstring afirma uma garantia que
nenhum teste cobra. A regra continua a mesma — *toda garantia nova vem com o
teste que a comprova* —, e esta ocorrência acrescenta: **garantia antiga que
muda de condição também.**

## Verificações novas

- `test_executor.py`: 401 e 403 param na primeira chamada com concorrência 1; com
  concorrência 4, no máximo 4 pedidos saem; 429, 500, 529 e falha sem status não
  param. Mutação: tornar `recusar` inócuo reprova quatro testes. A rodada
  interrompida e a de erro de segurança deixam a marca `INCOMPLETA`; a completa,
  não. Mutação: não apagar a marca reprova nove testes.
- `test_cli.py`: chave com caractere impossível (inclusive o caso real do
  piloto) e chave sem o prefixo param **antes** de qualquer pedido; o `run` para
  no primeiro 401, e o `score` recusa o bruto que ele deixou; o `freeze` em pasta descartável respeita as suítes do projeto,
  com e sem `--congeladas`, e o contrafactual (apontar para o vazio) reprova.
- `test_segredos.py`: forma da chave, e a chave recusada nem é citada nem
  registrada.
- O gerador do lote não emite mais âncora YAML (`&id001`). As quatro `nomes-*`
  mudaram de bytes, **não de conteúdo** — conferido pelo YAML parseado —, e não
  sobem versão.

## Próximos passos

1. **Segundo piloto** nos mesmos dois modelos, com as tarefas consertadas. Se os
   seis defeitos não reaparecerem, **congelar a v0.2**.
2. **Recomendado, a decidir:** rodar um terceiro modelo, de outro fornecedor,
   **antes** de endurecer as cinco famílias que ninguém errou. Endurecer com
   base em dois modelos da mesma casa seria ajustar o benchmark a eles.

## Dívidas que continuam abertas

As da ADR 0012: o braço de ablação dos identificadores, a decisão sobre o schema
congelado, o juiz que não existe, e a revisão humana das armadilhas.
