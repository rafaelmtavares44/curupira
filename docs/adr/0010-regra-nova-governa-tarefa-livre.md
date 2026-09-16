# ADR 0010 — Regra nova governa tarefa livre, e convenção comum mora num lugar só

- **Status:** aceita
- **Data:** 2026-09-16
- **Contexto de:** Entrega 17, correção do molde antes de produzir em escala
- **Relacionada a:** ADR 0008 (suíte congelada é imutável), ADR 0009 (nenhum default depende de locale)

## Contexto

A ADR 0009 corrigiu um viés escondido num default. Ao apresentar a família
`data-ambigua` como molde para as ~52 tarefas restantes, apareceu um segundo
defeito nas mesmas quatro tarefas — de outra natureza.

O `parity_notes` do `t2-date-0002` era **cópia do `t2-date-0001`**, e afirmava:

> *"aqui as duas versões têm a MESMA ambiguidade intrínseca. `05/03/2026` lido
> como mês-dia e `03/05/2026`..."*

Essas datas são do `0001`. O `0002` usa `19/08/2026` e `08/19/2026`, e **não tem
ambiguidade nenhuma** — o dia é 19, maior que 12, e essa é exatamente a razão de
ele existir: ele é o **controle**, não a armadilha. A nota descrevia o oposto da
função da tarefa.

O lint exige `parity_notes` não-vazio. Ele não lê o que está escrito lá.

## Por que a nota estava longa demais para ser lida

O campo tinha dezoito linhas. **Doze delas eram convenção do projeto**,
idênticas em todo arquivo do dataset: identificadores em português, o que muda
entre as versões, por que o controle existe. O trecho específico daquele par
ficava enterrado no meio.

Um campo assim não é documentação; é ruído com o nome de documentação. E a
prova é o que aconteceu: a tarefa passou por revisão humana atenta, com ADR
citada nos comentários, e ninguém notou que a nota falava de outra tarefa.

## D1 — Convenção comum sai dos arquivos e vai para `tasks/README.md`

Escrita **uma vez**. O `parity_notes` de cada tarefa diz o que muda **naquele
par**, e nada mais.

O README cobre: identificadores em português, as três ferramentas obrigatórias,
armadilha e controle por família, `family_id` como unidade de reamostragem,
dados sintéticos, canários, réguas registradas, paridade declarada e
imutabilidade da suíte congelada.

## D2 — Lint `notas-de-paridade-especificas`, com teto de tamanho

Nenhum lint confere se uma nota é **verdadeira**. O que dá para automatizar é
mantê-la **curta o bastante para ser lida**: teto de 700 caracteres.

É um portão indireto e está declarado como tal. Ele não teria pego a nota
errada; teria pego a nota longa que escondeu a nota errada.

### O portão que eu não consegui escrever

Tentei três desenhos antes deste, e os três falham:

| tentativa | por que não serve |
|---|---|
| acusar `parity_notes` **idêntico** entre pares diferentes | os pares `money-0001` e `money-0002` têm notas byte a byte idênticas, e **corretamente**: a justificativa de paridade é a mesma para os dois. Seria falso positivo em cima de tarefa congelada |
| extrair valores literais da nota e cobrar que apareçam na tarefa | exige uma regex do que conta como "valor literal". Frágil nos dois sentidos, e a primeira tarefa com formato novo quebra a regra |
| juiz LLM lendo a nota contra a tarefa | a camada 4 de pontuação é para texto livre do **agente**, não para auditar o nosso dataset. Usar juiz onde um validador serve é o que o escopo proíbe |

Fica declarado: **o conteúdo do `parity_notes` não é verificável por máquina
hoje.** O teto reduz a superfície onde um erro desses se esconde, e é o que há.

## D3 — Regra nova só governa tarefa livre

Este é o ponto que vale além deste caso.

O teto de 700 caracteres reprovaria os pares `money-*`, que têm cerca de 1100 —
e que estão **congelados na v0.1**. Obedecer à regra nova exigiria editá-los, e
editá-los é exatamente o que o `congelada-mudou` da ADR 0008 proíbe. As duas
regras juntas formariam um beco sem saída, e o `validate --strict` do CI ficaria
vermelho sem conserto possível.

A saída não é abrir exceção; é enunciar o princípio:

> **Uma regra escrita depois do congelamento governa o que ainda pode mudar.**
> O que já foi congelado é julgado pelas regras que existiam quando foi
> congelado, e corrigido por errata quando estiver errado.

`ids_congelados(suites)` reúne os ids de toda suíte, e uma regra escopada
consulta esse conjunto. Vale para toda regra futura, não só para esta — e vai
valer muitas vezes, porque o dataset vai crescer mais rápido que as convenções
se estabilizam.

## D4 — O teste do dataset real passou a carregar as suítes reais

`test_dataset_real_do_repositorio_passa_no_lint` chamava
`lint_do_dataset(tarefas, estrito=True)` **sem as suítes**. Lintava um mundo em
que nada foi congelado — que não é o mundo do `curupira validate`, nem o do CI.

Foi esse teste que reprovou quando a D3 entrou, e reprovou **pelo motivo
errado**: não porque o dataset estava mau, mas porque o teste e o comando real
divergiam.

É a segunda vez nesta base que a divergência entre o teste e o comando de
verdade custa uma rodada; a primeira foi o `ci.yml` rodando uma segunda cópia
do `detect-secrets` sem os argumentos do pre-commit. O teste agora carrega
`carregar_suites(raiz/"suites")` e afirma que encontrou alguma.

## Consequências

1. As quatro tarefas `t2-date-*` têm notas reescritas: curtas, específicas e
   verdadeiras. A do `0002` agora diz que ela é o controle, que é o que ela é.
2. `tasks/README.md` passa a ser o lugar da convenção. Tarefa nova não repete
   nada dele.
3. As tarefas `money-*` continuam intactas e congeladas. Suas notas longas são
   um registro histórico legítimo, não uma dívida a pagar.
4. Escrever tarefa ficou mais barato: o cabeçalho caiu de dezoito linhas para
   seis, e a parte que sobrou é a que exige pensar.

## Risco declarado

**O teto é uma métrica de tamanho servindo de proxy para qualidade**, e proxy
sempre pode ser satisfeito sem que a coisa real melhore: uma nota de 690
caracteres pode ser tão copiada quanto uma de 1100. O que o teto compra é que a
nota copiada fica **visível** na revisão, em vez de enterrada.

Contra isso não há portão, só disciplina — e a disciplina já falhou uma vez
neste mesmo campo.

## Nota de método

Duas entregas seguidas, dois defeitos nas mesmas quatro tarefas, nenhum dos dois
encontrado por leitura. O que os encontrou foi **tentar explicar o molde para
outra pessoa** — escrever a tabela "armadilha vs controle" deixou óbvio que a
nota do controle dizia ser a armadilha.

Isso é um método, e vale registrar como tal: **antes de replicar um padrão, o
padrão é apresentado.** Explicar força a consistência que a revisão não força.
