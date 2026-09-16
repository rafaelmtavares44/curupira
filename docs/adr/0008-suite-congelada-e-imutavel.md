# ADR 0008 — Suíte congelada é imutável, e a errata é o caminho

- **Status:** aceita
- **Data:** 2026-09-16
- **Contexto de:** Entrega 14
- **Resolve:** a tensão de design registrada na ADR 0005 e reaberta na ADR 0006

## Contexto

A promessa do escopo é curta e categórica:

> *"A v0.1 continua rodável para sempre."*

Entre as Entregas 9 e 11, a v0.1 foi recongelada **três vezes**. Cada
recongelamento tinha justificativa própria e defensável — o `expect.accept` da
ADR 0005, o `family_id` da ADR 0006 — e o argumento foi sempre o mesmo: *"a v0.1
nunca foi publicada e só rodou como piloto"*.

O argumento é verdadeiro e continuará verdadeiro para sempre, sobre a suíte que
for atual. **A frequência é que era o sinal**, e ignorá-la mais uma vez
significaria escrever as ~60 tarefas do piloto sobre um mecanismo que já sabemos
que não segura.

## A solução já estava escrita

O `core/suite.py` descreve o caminho certo desde a Parte B:

> *"A errata resolve o engessamento sem quebrar a suíte: a suíte **não muda um
> byte** e a errata, append-only, lista as tarefas defeituosas."*

`Errata`, `EntradaDeErrata` com `defect` e `test_ref` obrigatórios,
`TETO_DE_ERRATA`, `suite_esta_morta()` — tudo implementado, testado e nunca
usado. Não faltava mecanismo. Faltavam duas coisas: **um portão que fechasse o
caminho errado**, e um teto que não estrangulasse suíte pequena.

## D1 — Tarefa congelada é imutável, e o lint cobra

Novo lint, **severidade erro**: uma tarefa que aparece em qualquer suíte de
`suites/` não pode mudar nem sumir.

```
[erro] congelada-mudou · t2-money-0001: esta congelada na suite 'v0.1' e o
conteudo mudou. Tarefa congelada e imutavel: reverta a edicao, ponha esta tarefa
na errata com o teste que reproduz o defeito, e crie a correcao como tarefa
NOVA, com id novo, na mesma family_id
```

A mensagem **ensina o conserto**, e isso é deliberado: um portão que só recusa
ensina a contornar. Há um teste que cobra as três peças da instrução na
mensagem — errata, id novo, mesma família.

Roda no `validate`, que está no CI, e no `suite freeze`, para que congelar uma
suíte nova não legitime uma edição indevida na anterior.

### O que isso faz com o `task_version`

Ele deixa de ser um contador vitalício e passa a valer só no período de
rascunho: **antes** do primeiro congelamento a tarefa é livre e a versão sobe à
vontade; **depois**, a tarefa não muda mais, então a versão para de subir.

Isso não é perda — é o campo ganhando semântica precisa em vez da que ele
fingia ter.

## D2 — Corrigir cria tarefa nova, na mesma família

O conserto de uma tarefa congelada defeituosa é:

1. a tarefa defeituosa **fica onde está**, intacta;
2. entra na errata, com o defeito descrito e o teste que o reproduz;
3. a correção nasce como **tarefa nova, id novo**, na **mesma `family_id`**;
4. a tarefa nova entra na próxima suíte, nunca na congelada.

A família compartilhada não é detalhe: pela ADR 0006, o bootstrap reamostra
famílias, então a tarefa velha e a nova continuam contando como **uma
observação** — que é o que elas são.

`EntradaDeErrata` ganha **`replaced_by`**, opcional. Sem ele, o leitor vê uma
tarefa excluída e não sabe se foi consertada ou abandonada. As duas respostas
são legítimas; a ambiguidade não.

**Convenção de id:** o próximo número livre da família, não sufixo de letra.
`t2-money-0002` defeituosa vira `t2-money-0004`, e a `family_id` liga as duas.
Ids sequenciais não acumulam gramática.

## D3 — O teto da errata ganha um piso absoluto

O teto era 5%, puro. Numa suíte de duas tarefas isso dá 0,1: **a primeira errata
matava a suíte**. Na v0.1, com quatro tarefas, o mesmo.

O efeito era perverso e explica em parte o que aconteceu: o mecanismo desenhado
para evitar recongelamento era, na prática, a razão para recongelar. Usar a
errata matava a suíte; recongelar não.

```python
MINIMO_DE_ERRATAS_TOLERADAS = 2
tolerado = max(TETO_DE_ERRATA * len(congeladas), MINIMO_DE_ERRATAS_TOLERADAS)
```

Acima de quarenta tarefas o piso deixa de valer e o teto relativo volta a
mandar: 5% de sessenta são três, e três gabaritos errados num piloto desse
tamanho é motivo legítimo para encerrar a suíte em vez de remendá-la.

O piso é **folga, não licença**: a terceira errata mata uma suíte pequena do
mesmo jeito.

## Consequências

1. A v0.1 atual está congelada **de verdade**. O próximo defeito nela vira
   errata, não recongelamento.
2. `curupira validate` passa a carregar as suítes de `suites/`. Um dataset sem
   suíte nenhuma continua válido — é o estado de quem está começando.
3. `carregar_suites()` ignora `*.errata.yaml`, que mora no mesmo diretório e tem
   outro schema. Ler errata como suíte quebraria o `validate` por um arquivo
   legítimo.
4. Um teste de CLI que exigia que uma errata matasse a v0.1 foi **invertido**:
   agora ele exige que **não** mate. Era o comportamento errado, e estava
   congelado num teste.

## O que esta ADR não resolve

~~**A errata ainda é escrita à mão.**~~ **PAGO na Entrega 15.** `curupira errata
add` monta a entrada, confere o `test_ref` e recalcula se a suíte morreu;
`errata show` lista o que já entrou. O caminho certo deixou de ter mais atrito
que o errado, que era a causa dos três recongelamentos.

~~**O `test_ref` não é verificado.**~~ **PAGO EM PARTE na Entrega 15.**
`core/referencia.py` confere, por AST, que o arquivo existe e que define uma
função com aquele nome. **Continua em aberto** que o teste *falhe* na tarefa
defeituosa: isso exigiria executar o pytest, e o `curupira` é o pacote de
runtime. Qualquer teste verde com o nome certo passa.

**Nada impede uma suíte nova de nascer errada.** Este portão protege o que já foi
congelado. A qualidade da v0.2 depende do lint do dataset e da revisão humana,
como sempre dependeu.

> **Atualização de 2026-09-16 (ADR 0009):** a revisão humana já falhou nesse
> papel uma vez. Quatro tarefas novas, revisadas linha a linha, carregavam um
> viés de locale que estava no default de um matcher e não no YAML. A frase
> acima envelheceu mal em duas semanas, e a lição é a mesma da nota de método:
> o que segura é lint, não leitura.

## Nota de método

Esta é a terceira vez nesta sessão que a correção certa já estava escrita no
projeto e foi ignorada na prática: o comentário do `ci.yml` sobre CI e
pre-commit rodarem o mesmo comando, a `variant_group` que já descrevia famílias,
e agora a errata. **Documentação não é portão.** Cada uma dessas três virou
teste nesta sessão, e essa é a única forma que se mostrou eficaz.
