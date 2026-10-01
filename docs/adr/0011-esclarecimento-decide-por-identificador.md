# ADR 0011 — O esclarecimento decide por identificador, não por palavra-chave

- **Status:** aceita
- **Data:** 2026-10-01
- **Contexto de:** Entrega 18, pré-requisito do lote do piloto
- **Relacionada a:** ADR 0006 (família como unidade), ADR 0009 (nenhum default
  depende de locale), ADR 0010 (regra nova governa tarefa livre)

## Contexto

Antes de escrever o lote do piloto, recontei as famílias `strict` que a v0.1
consegue ter. O orçamento que eu tinha proposto prometia 13. Detalhando família
por família, sobraram **8**:

| proposta | o que era de verdade |
|---|---|
| separador de milhar | já existe: o `money-0002` ("paga 1.234") **é** isso, dentro de `separador-decimal` |
| percentual | separador decimal de novo — mesma competência, mesma família |
| número por extenso | compreensão de português, não formato brasileiro (T4) |
| multi-turno | o executor da v0.1 recusa `followup_turns` |

Contar como famílias separadas o que tem a mesma causa é o erro que a ADR 0006
condena: *famílias pequenas demais por descuido são o erro que produz o número
bonito.* A proposta cometia esse erro.

O número que importa é `N_MINIMO_PARA_BCA = 10` **famílias**. Com 8, o Delta da
v0.1 sairia rotulado como `amostra_insuficiente`.

O caminho natural para 10 eram famílias de esclarecimento — *"quando falta
informação, o agente pergunta ou inventa?"*, a pergunta central da T4. Antes de
propô-las, fui ver como o `clarify` é pontuado.

## O defeito

O docstring de `pontuar_clarify` dizia:

> *"2. Chamou `pedir_esclarecimento` mencionando todos os slots faltantes →
> acerto, camada AST. **Nada de léxico, nada de juiz.**"*

O código exigia que o slot aparecesse **por palavra-chave** — no texto da
resposta ou em **qualquer** argumento de **qualquer** chamada. As palavras-chave
vêm do YAML de cada versão do par:

| versão | o agente pergunta | a tarefa precisa declarar |
|---|---|---|
| pt-BR | "Qual dia?" | `dia` |
| en-US | "Which day?" | `day` |

Duas listas escritas à mão, uma por idioma. Uma lista mais pobre num idioma tira
ponto daquele idioma por culpa nossa. É a família de defeito da ADR 0009 — régua
que depende de locale — num lugar que o `par-mesma-regua` não vê, porque ele só
compara `arg_specs`.

E havia um sintoma de que o desenho estava frouxo: dois testes passavam
`args={"campo": "favorecido"}`. O argumento nem se chama `campo`. Passavam porque
o código aceitava a palavra em qualquer argumento.

## D1 — `campo_faltante` é um `enum` dos argumentos de negócio

```yaml
- name: pedir_esclarecimento
  parameters:
    properties:
      campo_faltante: {type: string, enum: [data_iso, titulo]}
```

O `enum` lista os nomes de argumento das ferramentas de negócio. Pela convenção
do `tasks/README.md`, esses nomes ficam em português **nas duas versões do par**.

"Slot" passa a ser o que sempre deveria ter sido: **o argumento que faltou.**

## D2 — O caminho da ferramenta decide por igualdade exata

`pontuar_clarify` agora tem três caminhos, sem sobreposição:

1. chamou ferramenta de negócio → **inventou**, falha AST;
2. chamou `pedir_esclarecimento` → os `campo_faltante` pedidos, somados entre
   chamadas, cobrem os `missing_slots` por **igualdade exata**? Passa ou falha
   na camada AST. **O texto da pergunta não é lido**;
3. não chamou a ferramenta → caminho da prosa, lexical como antes, exigindo
   interrogação.

O item 2 não ler o texto é deliberado. Se lesse, "para quem?" na `pergunta`
cobriria o slot mesmo com o `campo_faltante` errado, e o léxico voltaria pela
porta dos fundos. Há um teste que cobra isso.

`recusar` deixa de contar como pergunta num `clarify`: ela não diz o que falta.

## D3 — Dois lints, só para tarefa livre

- **`esclarecimento-por-identificador`** (erro): quem oferece
  `pedir_esclarecimento` declara o `enum` **igual** aos argumentos de negócio.
  Faltando um, aquele argumento fica impossível de pedir; sobrando, convida o
  agente a pedir o que não existe.
- **`slot-e-identificador`** (erro): todo `missing_slot` é um desses nomes. Um
  slot fora do `enum` torna a tarefa impossível de acertar pela ferramenta — a
  mesma classe de defeito da ferramenta proibida inexistente, na T5.

As duas seguem a ADR 0010: as `money-*`, congeladas antes da convenção, não são
cobradas. As `date-*`, ainda rascunho, ganharam o `enum`.

## D4 — O ensaio de congelamento roda no mundo real

`test_dataset_real_congela` ensaiava o `suite freeze` num destino **vazio**. As
`money-*` apareciam como livres e reprovavam a regra nova — que, no mundo real,
não se aplica a elas. Agora o teste copia `suites/` junto.

É a **terceira** vez que um teste linta um mundo que não existe: o `ci.yml` com
a segunda cópia do `detect-secrets`, o teste do lint sem suítes (ADR 0010 D4), e
este. O padrão é sempre o mesmo: o teste monta o ambiente à mão e esquece uma
peça que o comando real tem.

## O orçamento revisto

| trilha | famílias |
|---|---|
| T2 | `separador-decimal` ✓, `data-ambigua` ✓, `hora-12-24` |
| T1 | `escolha-de-ferramenta`, `ferramenta-em-ingles`, `nomes-compostos`, `anafora`, `irrelevancia` |
| T4 | `falta-argumento`, `referente-ambiguo`, `numero-por-extenso` |

**11 famílias.** A 11ª é margem deliberada: exatamente 10 seria frágil, porque
basta eu mesmo descobrir uma duplicata para o Delta voltar a
`amostra_insuficiente`.

Trazer T4 para a v0.1 é desvio do roadmap, e está registrado aqui como tal.

## Riscos declarados

**Um agente pode respeitar o `enum` de forma diferente conforme o idioma.** O
identificador é `data_iso` nos dois lados; um agente num contexto em inglês
talvez tenha mais tendência a escrever `date`. Isso seria uma assimetria real —
mas de **comportamento do agente**, não da nossa régua, e a falha sai rotulada
(`campo_faltante` fora do esperado) para poder ser contada à parte. Se aparecer
nos dados, vira achado; não é algo a corrigir no pontuador.

**O caminho da prosa continua lexical.** Um agente que pergunta sem chamar a
ferramenta ainda é julgado por palavras-chave escritas por idioma. A fração
decidida assim sai como `ABSTEVE` e `PENDENTE_DE_JUIZ`, separada do `PASSOU`, e
é reportada. É a dívida que sobra.

**A v0.2 vai misturar convenções.** As `money-*` oferecem `pedir_esclarecimento`
com `campo_faltante` livre; as tarefas novas, com `enum`. Como as `money-*` são
`tool_call`, a forma da ferramenta de abstenção não entra na nota delas — mas o
contexto que o agente vê é diferente, e isso fica dito.

## Nota de método

Quarto docstring nesta base que prometia o que o código não fazia: o `data_iso`
(*"o matcher não adivinha idioma"*), o comentário do `ci.yml`, o `variant_group`,
e agora o `pontuar_clarify`. Nenhum foi achado lendo o docstring — todos foram
achados **tentando usar** a peça para algo novo.
