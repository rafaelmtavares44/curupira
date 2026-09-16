# Convenções do dataset

Este arquivo existe porque a alternativa não funcionou. As convenções abaixo
estavam repetidas no `parity_notes` de cada tarefa — doze linhas iguais em todo
arquivo — e o efeito foi o oposto do pretendido: o campo ficou longo demais para
ser lido, e uma nota **copiada de outra tarefa**, descrevendo datas que não
estavam naquele arquivo, passou por revisão humana sem ser notada.

Convenção que vale para o dataset inteiro se escreve **uma vez, aqui**. O
`parity_notes` de cada tarefa diz o que muda **naquele par**, e nada mais.

> O lint `notas-de-paridade-especificas` cobra o teto de tamanho. Ele vale só
> para tarefa **livre**: as tarefas congeladas na v0.1 nasceram antes desta
> convenção e são imutáveis (ADR 0008).

---

## Identificadores ficam em português nas duas versões

Numa tarefa `parity: strict`, o nome da ferramenta e os nomes dos argumentos são
**idênticos** nas versões pt-BR e en-US, e ficam em português:

```yaml
# nas DUAS versões
- name: agendar_reuniao
  parameters:
    properties:
      data_iso: {type: string}
      titulo:   {type: string}
```

Traduzi-los mudaria duas coisas ao mesmo tempo, e o Delta PT-BR deixaria de
isolar a língua natural — passaria a medir também a tradução do esquema.

**Só mudam de idioma:** a `description` da ferramenta e a `input.user_message`.

Isto não é um limite do benchmark; é o controle experimental dele. O caso
"ferramenta descrita em inglês com usuário falando português" é uma trilha
própria, a T1, onde a diferença é o objeto de estudo e não ruído.

## Toda tarefa oferece as três ferramentas

A do domínio, mais as duas de abstenção:

```yaml
- name: pedir_esclarecimento   # faltou informação para executar com segurança
- name: recusar                # não é possível ou não é apropriado executar
```

Elas tornam a abstenção **detectável por AST**: um agente que quer perguntar
chama uma ferramenta, e chamada é o que o harness observa. Sem elas, medir
abstenção exigiria um léxico de hedge — que não é equivalente entre idiomas e
contaminaria o Delta com a nossa própria lista de palavras.

## Duas variantes por família: a armadilha e o controle

Cada família traz ao menos duas tarefas no mesmo `variant_group`, com
**gabaritos diferentes**:

| variante | papel |
|---|---|
| a **armadilha** | o caso ambíguo, onde a convenção brasileira e a anglófona divergem |
| o **controle** | o caso equivalente sem ambiguidade nenhuma |

Exemplo, na família `data-ambigua`: `05/03/2026` é ambíguo; `19/08/2026` não é,
porque 19 não pode ser mês.

Quem erra as duas não tem problema com a convenção — tem problema com a
conversão. Quem erra só a armadilha tem o problema que o Curupira existe para
medir. **Sem o controle, as duas hipóteses se confundem no agregado**, e o
número publicado seria maior do que o defeito real.

## `family_id` é a unidade de reamostragem

As tarefas de uma família não são observações independentes: quem entende a
convenção acerta a família inteira. O bootstrap do Delta reamostra **famílias**,
não tarefas (ADR 0006) — declarar `family_id` errado infla a confiança do
resultado.

O `family_id` é o mesmo nas duas versões do par. O `pair_id` é o que liga uma
versão à outra.

## Nenhum dado de pessoa real, em hipótese alguma

Todo documento, CPF, CNPJ, CEP, telefone e nome é **sintético e gerado
proceduralmente** — CPF válido sai do algoritmo do dígito verificador, nunca
copiado de ninguém. Documentos sintéticos não imitam a identidade visual de
nenhuma empresa ou órgão existente.

Exigência de LGPD, é a coisa certa a fazer, e vira seção do artigo.

## Cada tarefa carrega um `canary_guid` único

No estilo BIG-bench. Serve para duas coisas: pedido explícito de exclusão do
treino, legível por crawler; e detector de contaminação — se meses depois um
modelo souber o GUID, o dataset vazou e há prova.

Canário duplicado arruína a segunda função: você sabe que vazou, mas não sabe
qual tarefa. O lint `canario-unico` cobra isso.

## Régua: matchers e validadores são nomes registrados

Nunca lógica embutida no YAML. O dataset é declarativo e auditável por humano; a
lógica vive em Python, testada e coberta.

Nenhum default do harness pode depender de locale (**ADR 0009**). Onde a régua
admite convenção — datas, por exemplo — a tarefa **declara** os formatos
aceitos, e declara **os mesmos nos dois lados do par**. Dois lints cobram isso:
`regua-de-data-explicita` e `par-mesma-regua`.

## Paridade declarada

| `parity` | significado | entra no Delta? |
|---|---|---|
| `strict` | mesma tarefa, mesma dificuldade, só o idioma muda | **sim** |
| `localized` | adaptada culturalmente (endereço, moeda, documento) | não |
| `br_only` | sem par possível (dígito verificador de CPF, boleto) | não |

O Delta PT-BR se calcula **exclusivamente** sobre `strict`. Afrouxar isso daria
um número maior e indefensável.

## Tarefa congelada é imutável

Uma tarefa que entrou numa suíte de `suites/` não muda mais — nem um byte. Se
estiver errada: ela fica onde está, entra na **errata** com o teste que
reproduz o defeito, e a correção nasce como **tarefa nova, id novo, mesma
família** (ADR 0008).

Antes do primeiro congelamento a tarefa é rascunho e pode mudar à vontade.

```powershell
curupira errata add --suite v0.1 --tarefa <id> --defeito "..." --test-ref "tests/test_x.py::test_y"
```
