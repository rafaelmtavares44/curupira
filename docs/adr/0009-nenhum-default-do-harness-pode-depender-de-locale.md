# ADR 0009 — Nenhum default do harness pode depender de locale

- **Status:** aceita
- **Data:** 2026-09-16
- **Contexto de:** Entrega 16, primeira família de tarefas depois da `money-*`
- **Relacionada a:** ADR 0005 D3 (assimetria declarada), ADR 0007 D4 (resposta sem idioma)

## Contexto

A segunda família do dataset, `data-ambigua`, entrou com quatro tarefas: duas em
PT-BR, duas em EN-US, `parity: strict`, `arg_specs` **idênticos** nos dois lados
do par, revisadas linha a linha e aprovadas pelo `validate --strict`.

Estavam erradas.

O matcher `data_iso` tinha um default:

```python
FORMATOS_DE_DATA_PADRAO = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")
"""`%d/%m/%Y` primeiro: e a convencao brasileira, e o dataset nasce em PT-BR."""
```

A justificativa é verdadeira e a consequência é grave. Considere um agente que
**não faz o trabalho** — devolve a data exatamente como o usuário escreveu, sem
converter para ISO:

| versão | mensagem | agente devolve | régua padrão lê | gabarito | resultado |
|---|---|---|---|---|---|
| pt-BR | `05/03/2026` | `"05/03/2026"` | 5 de março | 2026-03-05 | **acerta** |
| en-US | `03/05/2026` | `"03/05/2026"` | 3 de maio | 2026-03-05 | **erra** |

O mesmo não-trabalho vale ponto em português e não vale em inglês. O Delta
PT-BR, que existe para medir *quanto o agente piora quando o usuário fala
português*, ganharia pontos **na direção oposta**, gerados pelo próprio
Curupira.

## O que torna este defeito perigoso

Ele é **invisível na revisão do dataset**. Os dois YAMLs eram idênticos no
trecho que importa:

```yaml
data_iso: {matcher: data_iso}
```

Nenhum lint reclamava, nenhum teste falhava, e uma leitura atenta dos dois
arquivos lado a lado não acusa nada — porque o viés não está no que foi
escrito, está no que foi **omitido**. O default mora no código, longe do dado, e
o dado parece simétrico.

É a terceira vez que o projeto encontra a mesma forma de defeito: uma
assimetria entre os dois lados de um par strict, introduzida pelo harness e não
pelo agente. A ADR 0005 D3 teve de declarar a do separador decimal; a ADR 0007
D4 eliminou a da resposta da ferramenta em português. Esta é a primeira que
sobreviveu a uma revisão humana.

## D1 — `data_iso` não tem default; `formatos_aceitos` é obrigatório

Omitir o parâmetro agora estoura com `ValueError`, e a mensagem diz por quê. O
docstring do matcher já prometia *"a régua vem da tarefa — o matcher não adivinha
idioma"*, e o código embaixo fazia exatamente o contrário. A promessa virou
código.

## D2 — Lint `regua-de-data-explicita`, severidade erro

O `ValueError` é a rede; o portão é o lint, que roda no `validate` e portanto no
CI. Uma tarefa com `data_iso` sem `formatos_aceitos` não passa do lint, e a
mensagem manda declarar **os mesmos formatos nas duas versões do par**.

Lista vazia não conta como declarada: `formatos_aceitos: []` é a maneira mais
fácil de calar um lint sem resolver nada, e tem teste que cobra isso.

## D3 — Lint `par-mesma-regua`, severidade erro

Regra irmã, para o caso que o revisor enxergaria e ainda assim deixaria passar:
num par `strict`, o conjunto `(campo, matcher, parâmetros)` tem de ser idêntico
nos dois lados. Matcher diferente, limiar diferente, ou um argumento medido só
de um lado — os três acusam.

A comparação é canônica, então a mesma régua escrita com as chaves em outra
ordem continua sendo a mesma régua.

O motivo de ser **erro** e não aviso é o incentivo: quem escreve a tarefa
escolhe as duas réguas e publica o número que sai delas. É o mesmo raciocínio do
`par-idiomas-diferentes`, que já está no projeto.

## D4 — A régua das tarefas de data é ISO, e só ISO

As quatro tarefas `t2-date-*` passaram a declarar
`formatos_aceitos: ["%Y-%m-%d"]`, nas duas versões.

O argumento se chama `data_iso` e o schema da ferramenta pede ISO: devolver a
data na grafia da entrada **não é a conversão que a tarefa cobra**. Aceitá-la
premiaria o não-trabalho — e, como a tabela acima mostra, premiaria mais em
português do que em inglês.

A alternativa considerada era dar a cada versão a régua do seu locale (`%d/%m/%Y`
para PT-BR, `%m/%d/%Y` para EN-US). Ela também é simétrica, e foi recusada por
outro motivo: aceitaria a não-conversão como correta nos **dois** idiomas,
destruindo a armadilha inteira. A tarefa existe para medir se o agente converte.

## Auditoria dos outros matchers

A regra do título só vale se for verificada no resto do código, não só no lugar
onde o defeito apareceu:

| matcher | default sensível a locale? | por quê |
|---|---|---|
| `para_centavos` / `moeda_normalizada` | **não** | a política é *"o separador que aparece por último é o decimal"* — resolve `1.234,56` e `1,234.56` sem consultar idioma. Simétrica por construção |
| `fuzzy_name` | **não** | `ignorar_acentos` já é `True` por padrão. Fosse `False`, o agente que escrevesse `Jose` por `José` perderia ponto na versão PT-BR e não teria como perder o equivalente na EN-US |
| `exact_int`, `exact_str`, `one_of` | **não** | comparação literal, sem normalização de locale |
| `por_validador` | **não** | os validadores são de formato brasileiro e as tarefas que os usam são `br_only`, que não entram no Delta |

Nenhuma correção adicional foi necessária. O `fuzzy_name` passou por pouco, e
por acidente: o default certo estava lá, sem que ninguém tivesse escrito o
motivo. Agora está escrito.

## Consequências

1. Toda tarefa de data declara sua régua. É mais verbosa, e a verbosidade é o
   ponto: o que o Delta mede fica no dado, não no código.
2. `FORMATOS_DE_DATA_PADRAO` deixou de existir. Não há como herdar o viés.
3. Quatro testes de matcher que usavam o default foram reescritos para declarar
   a régua — e ficaram melhores, porque agora mostram a mesma grafia dando
   resultados opostos conforme a régua declarada.
4. **A v0.1 não é afetada.** As tarefas `money-*` usam `exact_int` e continuam
   congeladas, byte por byte. As `date-*` ainda são rascunho e podem mudar à
   vontade — que é exatamente o período em que a ADR 0008 diz que a tarefa é
   livre.

## Risco declarado

**Esta ADR corrige um caso e enuncia uma regra; ela não prova que a regra é
completa.** A auditoria acima é uma leitura atenta do código de hoje, não um
portão. Um matcher novo com default sensível a locale passaria sem ser notado, e
o `regua-de-data-explicita` só conhece o `data_iso`.

O portão que faltaria seria estrutural: proibir default em qualquer parâmetro
que altere o resultado conforme o idioma. Não sei ainda escrever esse teste sem
uma lista mantida à mão — que é a mesma dívida do `MATCHER_DE_DATA`, só que
maior. Fica aberto e declarado.

## Nota de método

Quatro arquivos revisados linha a linha, com ADR citada nos comentários, e o
defeito estava no código que eles não mencionavam. A revisão humana encontrou
tudo o que estava escrito e nada do que estava omitido — o que é exatamente o
que se deve esperar dela.

Este é o quarto registro da mesma lição, e o mais caro se tivesse passado: a
ADR 0008 já dizia que **documentação não é portão**. Comentário no YAML também
não é. O que segurou foi um teste que estoura e um lint que reprova.
