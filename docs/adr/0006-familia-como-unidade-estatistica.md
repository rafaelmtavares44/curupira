# ADR 0006 — A família como unidade estatística, e a saída do valor-p

- **Status:** aceita
- **Data:** 2026-09-16
- **Contexto de:** Entrega 11
- **Relacionada a:** ADR 0005, pendência P2 do escopo

## Contexto

O piloto vai ter ~60 tarefas, e elas não vão nascer uma a uma: vão nascer de
moldes. Dez variações da armadilha do separador decimal, oito de data ambígua,
seis de detecção de irrelevância. É assim que se escreve dataset, e é a única
forma de chegar a sessenta tarefas com qualidade.

Isso cria um problema que o harness ainda não via. **Tarefas do mesmo molde não
são observações independentes.** Quem entende o separador decimal brasileiro
acerta as dez; quem não entende erra as dez. São uma observação, não dez.

O `bootstrap_bca` já reamostrava **pares** em vez de repetições, e o raciocínio
estava escrito no código desde a Parte B:

> *"reamostrar repetições em vez de pares trataria as k repetições de uma tarefa
> como observações independentes, e elas não são — o intervalo sairia estreito
> demais, o que é o erro que mais engana."*

A frase está certa e continua valendo. Ela só parava um nível cedo demais.

Com o dataset atual — quatro tarefas, dois pares — o problema era invisível. Com
sessenta, ele é a diferença entre um intervalo de confiança honesto e um
intervalo bonito.

## D1 — `family_id`, campo novo, escopado por par

### O que foi considerado

Já existia `variant_group`: *"grupo de variantes próximas com gabaritos
DIFERENTES, escopado por locale, detector de acertou por sorte"*. A semântica
quase serve — "quem entende o molde acerta o grupo inteiro" é exatamente a
dependência que a reamostragem quer capturar.

**Reusá-lo foi descartado por dois motivos concretos, não estéticos:**

1. **O escopo está errado.** `variant_group` é escopado por locale (`g1` e
   `g1-en` são grupos distintos), mas a unidade do Delta é o **par**, que
   atravessa os dois idiomas. Reusar obrigaria a *derivar* a família do par a
   partir do grupo da versão PT-BR — inferência onde o projeto já decidiu, no
   `ruff.toml`, que *"portão que depende de adivinhação não é portão. Declare,
   não infira."*
2. **O lint de `variant_group` exige gabaritos diferentes**, e isso barraria uma
   família legítima que aparece já na T1: várias tarefas de detecção de
   irrelevância, todas com `expect: no_tool_call`. Mesmo gabarito, mesma família
   óbvia, lint recusa.

### Decisão

Campo novo, `family_id`, **escopado por par**. As duas versões de um `pair_id`
carregam a mesma família, e o lint recusa divergência.

Os dois campos convivem com papéis separados e uma relação declarada:

| | `variant_group` | `family_id` |
|---|---|---|
| mede | acertou por sorte? | dependência estatística |
| escopo | um locale | o par, nos dois locales |
| gabaritos | precisam diferir | podem repetir |
| usado por | consistência de grupo | bootstrap do Delta |

**Todo grupo de variantes está contido numa família.** Se duas tarefas são
variantes próximas, vieram do mesmo molde. A recíproca é falsa. O lint cobra a
contenção, para que os dois campos não divirjam em silêncio.

### Severidade, e por que ainda não é erro

Três regras novas no lint:

| regra | severidade | o que pega |
|---|---|---|
| `familia-do-par` | **erro** | as duas versões de um par declaram famílias diferentes |
| `familia-do-grupo` | **erro** | um `variant_group` se espalha por famílias diferentes |
| `familia-declarada` | **aviso** | tarefa `parity: strict` sem `family_id` |

A terceira é aviso, e não erro, por uma razão de sequência: transformá-la em
erro hoje obrigaria a mexer em toda tarefa existente. **Vira erro quando o
piloto for autorado** (Entrega 12), porque a partir dali toda tarefa nasce com
família e um `None` passa a ser esquecimento, não legado.

`None` significa "família de um membro só" e é tratado como tal no bootstrap,
com rótulo `par:<pair_id>` para não colidir com um `family_id` homônimo.

## D2 — O bootstrap reamostra famílias

Cada réplica sorteia `n_familias` famílias **com reposição** e toma a média de
todas as diferenças das famílias sorteadas. O tamanho total varia entre
réplicas, porque famílias têm tamanhos diferentes: é o comportamento correto do
bootstrap de cluster, não um defeito a corrigir.

Duas consequências que valem ser ditas em voz alta:

- **O jackknife da aceleração passa a deletar famílias inteiras.** Deletar pares
  trataria membros da mesma família como trocáveis — a suposição que a
  clusterização recusa.
- **`N_MINIMO_PARA_BCA` passa a contar famílias.** Cem pares em três famílias
  são três observações independentes, e o relatório tem de dizer
  `amostra_insuficiente` em vez de produzir um intervalo com duas casas
  decimais.

### Compatibilidade, e como ela é provada

Com uma família por par, o bootstrap de cluster **degenera exatamente** no
bootstrap simples. Por isso as constantes conferidas contra o scipy continuam
valendo, e existe um teste dedicado a essa equivalência
(`test_familias_singleton_reproduzem_o_bootstrap_por_par`): se ele cair, a
mudança alterou o método, não só a unidade.

E um teste prova que a mudança faz o que promete
(`test_reamostrar_familias_alarga_o_intervalo`): doze pares correlacionados em
três famílias produzem intervalo **mais largo** do que os mesmos doze tratados
como independentes.

## D3 — O relatório deixa de ter valor-p

### O que motivou

Corrigir só o intervalo deixaria metade do problema publicado: `mcnemar_exato` e
`wilcoxon_pareado` também assumem pares independentes.

### O que foi considerado

1. **Agregar por família antes do teste.** Honesto, e descartado: com ~12
   famílias num piloto de 60 tarefas o teste quase nunca daria significativo
   mesmo com efeito real, e `p = 0,21` seria lido como "não há efeito" quando
   significa "não há amostra". Trocaria um número otimista por um pessimista.
2. **Manter o teste por par e rotular o valor-p como otimista.** Publicar um
   número sabidamente errado com nota de rodapé. O leitor memoriza o número, não
   a nota.
3. **Sair do produto.**

### Decisão

A **3**. O relatório reporta o Delta e o intervalo de confiança, e mais nada.

O argumento decisivo é que **o IC já contém o teste**: um IC de 95% que não cruza
zero diz `p < 0,05`; um que cruza diz o contrário. Reportar os dois seria
redundância — e, no nosso caso, redundância *discordante*, porque o IC sairia de
um bootstrap por famílias e o valor-p de um teste por pares. Dois números de
universos diferentes na mesma tabela, e o menos correto é o que seria
memorizado.

Isso também é o que o escopo do projeto já dizia:

> *"O produto é 'o Delta do agente X é 12 pontos, IC 95% [6, 18]', não
> 'p < 0,05'."*

### O que NÃO foi decidido

**`mcnemar_exato`, `wilcoxon_pareado` e `discordantes` continuam no código**,
implementados e testados contra o scipy. O que saiu foi o valor-p do produto,
não as funções. Apagar código correto e coberto seria desperdício, e existe um
caminho plausível de volta: um valor-p coerente com a clusterização, por
inversão do IC bootstrap ou por permutação de famílias. Se ele for implementado,
entra pela porta da frente, com o mesmo padrão de conferência contra o scipy.

Um teste guarda essa intenção (`test_as_funcoes_de_teste_continuam_disponiveis`),
para que ninguém as remova por parecerem código morto.

## D4 — O relatório passa a exibir `n_familias`

`n_pares` sozinho, ao lado de um intervalo clusterizado, convida o leitor a achar
que a amostra é maior do que é. Os dois números aparecem juntos, e **o que vale
é o segundo**.

## Consequências

1. `task_version` sobe de 2 para 3 nas quatro tarefas do par, que passam a
   declarar `family_id: separador-decimal`. As duas são a mesma armadilha; o
   `variant_group` já dizia isso desde a Parte B.
2. **A suíte v0.1 é recongelada** — terceira vez. Ela nunca foi publicada e só
   rodou como piloto. A tensão registrada na ADR 0005 continua aberta e continua
   sendo pré-requisito da publicação.
3. **A rodada de 16/09 passa a ter `n_familias = 1`.** Os dois pares eram a
   mesma família o tempo todo. Se ela fosse re-agregada hoje, o método sairia
   como `amostra_insuficiente` em vez de produzir um intervalo — o que é a
   resposta certa, e que o relatório antes não dava. É a demonstração mais
   econômica do que esta ADR corrige.
4. `ResultadoDelta` perde `p_valor` e `teste`, ganha `n_familias`. O
   `report.json` muda de forma; como ele é só gravado, nunca relido pelo código,
   não há migração a fazer.

## O que esta ADR não resolve

**O aviso `familia-declarada` depende de alguém declarar a família certa.** O
lint cobra coerência — que o par não se parta, que o grupo não se espalhe — mas
não tem como saber se duas tarefas de moldes diferentes foram rotuladas com a
mesma família, nem o contrário. Isso é julgamento de quem autora, e a única
defesa é a regra da ADR 0005 D2 aplicada de novo: **ao autorar, pergunte de que
molde esta tarefa veio.**

O risco prático é rotular famílias grandes demais por conveniência, o que
alargaria os intervalos sem necessidade, ou pequenas demais por descuido, que é
o erro que produz o número bonito. Dos dois, só o segundo engana — e é por isso
que o aviso existe.

## Dívida que esta entrega paga

`windows-latest` entra na matriz do CI, com uma versão de Python só. O eixo que
esse job cobre é o sistema operacional, não o interpretador.

O motivo está escrito no próprio workflow: o bug de fim de linha da Entrega 10
existia desde a Entrega 1 e atravessou 780 testes verdes, porque o CI rodava só
em Linux e o desenvolvimento só acontecia no Windows — e nenhum dos dois,
sozinho, via o defeito.
