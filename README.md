<div align="center">

<img src="docs/curupira.svg" alt="Curupira" width="150">

# Curupira

**A sua IA fica mais burra quando você fala com ela em português?**

Todo mundo desconfia que sim. Ninguém tem o número.
Este projeto existe para produzi-lo.

[![CI](https://github.com/rafaelmtavares44/curupira/actions/workflows/ci.yml/badge.svg)](https://github.com/rafaelmtavares44/curupira/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![Código: Apache 2.0](https://img.shields.io/badge/c%C3%B3digo-Apache--2.0-green)
![Dataset: CC BY 4.0](https://img.shields.io/badge/dataset-CC--BY--4.0-green)

</div>

---

## Começa com uma transferência bancária

Imagine uma inteligência artificial cuidando das contas da sua empresa. Você
manda uma mensagem:

> *"faz uma transferência de 1.234,56 pro fornecedor Silva"*

Mil duzentos e trinta e quatro reais e cinquenta e seis centavos. Qualquer
brasileiro lê assim sem pensar.

Só que a maior parte dessas inteligências artificiais foi construída por gente
que escreve números de outro jeito. Em inglês, aquele ponto não separa o milhar —
ele separa os centavos. Lido daquele jeito, `1.234,56` pode virar **um milhão
duzentos e trinta e quatro mil reais**.

Mil vezes mais.

E aqui está a parte que assusta: **ela não avisa.** Responde "transferência
criada com sucesso" e passa para a próxima tarefa. Você descobre no extrato.

O Curupira existe por causa disso.

## A diferença entre uma IA que conversa e uma IA que age

Quando uma IA erra numa conversa, você percebe na hora: ela escreveu bobagem,
você lê, você corrige.

Mas a nova geração não só responde — ela **executa**. Marca reuniões, emite notas
fiscais, cancela pedidos, transfere dinheiro. Quando essa erra, não sobra um
texto esquisito na tela: sobra estrago no mundo real.

Quase tudo que existe para testar essas IAs foi feito em inglês, por quem fala
inglês, imaginando um mundo em inglês. E quase todo teste que existe em português
mede se ela **conversa** bem, não se ela **executa** direito.

| | Mede agente? | Fala PT-BR? |
|---|---|---|
| BFCL V4 (Berkeley) | sim | não |
| CLARIN-PT-LDB (PROPOR 2026) | não | português europeu |
| Open PT LLM Leaderboard, PoETa v2, Prosa, LLM Fauna | não | sim |
| **Curupira** | **sim** | **sim** |

## Como ele descobre

Do jeito mais simples que existe: **aplicando a mesma prova duas vezes.**

Uma vez em inglês, uma vez em português. Mesma tarefa, mesma dificuldade, mesmas
ferramentas à disposição. Só o idioma muda. Depois compara as notas.

A diferença entre elas é o **Delta PT-BR**: o custo, em pontos, de falar a sua
própria língua com a sua própria IA. Esse número não existe hoje, e é a manchete
do projeto.

Parece óbvio, mas fazer isso **direito** é difícil, porque é fácil trapacear sem
querer. Se as duas provas não forem rigorosamente equivalentes, a diferença no
fim não mede o idioma — mede o descuido de quem montou a prova. Metade do
trabalho aqui é impedir esse tipo de acidente.

O Delta sai **exclusivamente** de pares marcados `parity: strict`, e **nunca** de
tarefas pontuadas por juiz LLM: um juiz LLM avaliando português degrada pela mesma
razão que estamos tentando medir.

## Não é prova de conhecimento. É prova de execução.

O Curupira não pergunta capitais nem datas. Ele dá uma tarefa e uma ferramenta, e
observa se a IA usa a ferramenta direito.

É a diferença entre perguntar a um motorista o que significa a placa de pare, e
sentar no banco do carona para ver se ele para.

| | Trilha | O que testa |
|---|---|---|
| **T1** | Tool calling em PT-BR | usar a ferramenta certa — e saber **não** usar nenhuma quando o pedido é impossível |
| **T2** | Formatos brasileiros | `1.234,56`, `dd/mm/aaaa`, CPF, CNPJ (inclusive alfanumérico), CEP, PIX, boleto, NF-e |
| **T3** | Documentos brasileiros | nota fiscal, boleto, contracheque, conta de luz, edital — todos sintéticos, inclusive tortos e escaneados |
| **T4** | Português real | WhatsApp sem acento, "vc", "pq", pedido incompleto. **Quando falta informação, ela pergunta ou inventa?** |
| **T5** | Segurança em português | o golpe que a IA recusa em inglês, ela recusa em português? |
| **T6** | Multi-turno com efeito colateral | ela confirma antes de apagar, quando o pedido vem em tom casual? |

## O erro que o projeto persegue

O nome disso aqui dentro é **falha silenciosa**: errar e entregar com cara de
acerto, sem dar ao humano a chance de perceber.

Um teste comum diz "acertou 70%". O Curupira diz *como* ela errou nos outros
30% — e, principalmente, se errou **do jeito específico de quem está pensando em
inglês**: lendo o ponto como vírgula, trocando o dia pelo mês, inventando um dado
que não foi dado.

Saber que errou é a nota. Saber como errou é o diagnóstico. E o diagnóstico é o
que permite consertar.

## O que ele recusa fazer

Um teste mal feito é **pior do que teste nenhum**. Teste nenhum te deixa inseguro,
e a insegurança te faz conferir. Um teste errado te dá um número bonito e te faz
dormir tranquilo.

- **Não chuta.** Quando a correção fica ambígua, a questão vira `pendente_de_juiz`
  e sai da conta, em vez de virar nota inventada. Chutar seria traiçoeiro aqui: as
  respostas confusas aparecem mais em um dos dois idiomas, e o chute entraria
  direto no Delta disfarçado de medição.
- **Não deixa a prova mudar escondido.** A lista de tarefas é lacrada com hash. Se
  alguém alterar uma vírgula depois do lacre, o programa para — em vez de produzir
  número errado calado.
- **Não esconde o óbvio.** Toda nota sai ao lado do que tiraria um "candidato
  burro" que responde sempre a mesma coisa. Se o agente não bate esse chão, não
  provou competência nenhuma. A comparação é **por trilha**: uma política
  degenerada gabarita uma trilha e zera as outras, e a média global esconderia
  exatamente isso.
- **Não inventa dinheiro.** "R$ 3,40 por acerto" exige tabela de preço com data e
  cotação com data. Sem isso, reporta em tokens, que não vencem.
- **Não usa IA para corrigir a prova.** Seria medir uma régua torta com outra
  régua torta.

## Uso

```bash
# 1. lint do dataset
curupira validate --strict

# 2. congelar uma suíte (id + task_version + sha256 de cada tarefa)
curupira suite freeze v0.1

# 3. ensaio: sem chave, sem rede, sem custo
curupira run --suite v0.1 --agent ensaio --modelo falso-1 --provedor falso

# 4. rodada de verdade (PowerShell)
$env:CURUPIRA_ANTHROPIC_API_KEY = "..."
curupira run --suite v0.1 --agent claude-baseline --modelo <modelo> `
  --provedor anthropic --repeticoes 5 --cache cache/

# 5. pontuar — sem provedor, sem custo, quantas vezes quiser
curupira score runs/v0.1__claude-baseline__<carimbo>

# 6. agregar: métricas por trilha, Delta PT-BR e linhas de base
curupira report runs/v0.1__claude-baseline__<carimbo>
```

Faça sempre o ensaio com `--provedor falso` antes da rodada paga: ele percorre o
mesmo caminho de arquivo, concorrência, cache e formato do bruto. O adaptador
falso não é andaime — é também a linha de base trivial do leaderboard.

Três recusas acontecem **antes** da primeira chamada paga: hash divergente do
congelado na suíte, tarefa da suíte ausente do dataset, e tarefa multi-turno (T6,
que só chega na v0.3). Descobrir qualquer uma delas na tarefa 200 custaria as
outras 199.

Sobre reprodutibilidade: a Messages API da Anthropic **não tem parâmetro de
seed**. Cada linha grava `seed_aplicada`, e nesse provedor ela é `false` — a
repetição mede não-determinismo, não reprodutibilidade bit a bit. Uma tupla que
listasse uma seed jamais honrada seria uma tupla que mente.

## Princípio de arquitetura

**Guarde o bruto, agregue tarde.** Três etapas, cada uma re-executável a partir do
disco:

```
executar  ->  runs/<id>/raw.jsonl      (resposta crua, argumentos exatos)
pontuar   ->  runs/<id>/scored.parquet (veredicto por repetição)
agregar   ->  runs/<id>/report.json    (acurácia, Delta, falha silenciosa)
```

Só a primeira etapa fala com o provedor. Rotular um modo de falha novo, aplicar
uma errata ou corrigir um matcher custa uma reexecução de `score` — segundos — em
vez de uma rodada paga.

## A estatística, e por que não há scipy aqui

`mcnemar_exato` usa a binomial, não a aproximação qui-quadrado: o número de
discordantes vai ser pequeno num piloto, e a aproximação mente justamente aí. O
intervalo de confiança sai de um bootstrap BCa que reamostra **pares**, com seed
fixa — reamostrar repetições trataria as k repetições de uma tarefa como
independentes, e o intervalo sairia estreito demais. O método **degrada e
declara**: com menos de 10 pares o campo `metodo_ic` diz `amostra_insuficiente`.

Tudo isso cabe em `math` e `statistics.NormalDist`. Somar ~30 MB de supply chain —
com janela de carência, lockfile com hash e pip-audit — por três funções seria mau
negócio. Os valores de referência em `tests/test_delta.py` foram conferidos contra
`scipy 1.17.1` e congelados como constantes: o CI não ganha dependência, o número
ganha testemunha.

## Ética e dados

Nenhum documento, CPF, CNPJ ou dado de pessoa real entra no dataset, em hipótese
alguma. Tudo é sintético e gerado proceduralmente, a partir dos algoritmos
públicos de formação e dígito verificador — um CPF que passa na validação, mas que
nasceu ali e não pertence a ninguém. Os documentos sintéticos também não imitam a
identidade visual de nenhuma empresa ou órgão existente.

**Declaramos deliberadamente que não verificamos os identificadores gerados contra
nenhuma base real**, porque fazê-lo exigiria tratar dados pessoais reais de
milhões de pessoas para proteger um dataset que não contém nenhum.

Procedimento de colisão: ver [SECURITY.md](SECURITY.md).

## Instalação (desenvolvimento)

```bash
git clone https://github.com/rafaelmtavares44/curupira
cd curupira
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows / PowerShell
# source .venv/bin/activate       # Linux / macOS

pip install -e ".[dev]"
pre-commit install
```

### Lockfile com hash (pendente)

O `pyproject.toml` fixa **versões exatas**. A segunda metade da postura de supply
chain da [ADR 0002](docs/adr/0002-camada-de-adaptadores.md) — fixar também por
**hash** — ainda não está no repositório, porque o lockfile precisa ser gerado no
sistema onde o projeto roda:

```powershell
pip install uv
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements.lock
```

Depois disso, trocar a linha do `pip-audit` no CI por
`python -m pip_audit --strict --require-hashes -r requirements.lock`.

**Política de carência:** nenhuma release com menos de 7 dias entra no lockfile.
As versões maliciosas do `litellm` (24/03/2026) viveram cerca de 5h30.

### Portão de qualidade

Nada entra na `main` sem passar:

```bash
ruff check .
ruff format --check .
mypy
bandit -c pyproject.toml -q -r src
pip-audit
pytest
```

## Estrutura

```
src/curupira/
  core/        modelo de dados: tarefa, expect, resultado, suíte, hash, registro
  formatos/    CPF, CNPJ, CEP, telefone, placa, PIX, boleto, NF-e
               (validar / gerar / corromper, com teste de propriedade)
  matchers/    matchers registrados por nome, usados pelo AST checker
  scoring/     os seis tipos de expect, falha silenciosa, gravação do pontuado
  adapters/    um adaptador por provedor, escrito à mão (ADR 0002)
  runner/      execução com escritor único e cache de resposta
  report/      agregação, Delta PT-BR, linhas de base triviais
  security/    redação de segredos (ver tests/test_segredos.py)
tasks/         o dataset, em YAML, declarativo e auditável por humano
suites/        suítes congeladas e erratas
docs/adr/      decisões registradas
```

## Estado do projeto

O examinador está pronto: sabe preparar a prova, aplicá-la, corrigi-la e calcular
o resultado com estatística séria. O pipeline inteiro roda de ponta a ponta.

O que falta agora são **as questões da prova**. Existem 4 escritas; o primeiro
estudo precisa de cerca de 60. A parte difícil de construir já está de pé — o que
vem agora é trabalho de autoria.

## Licenças

- **Código:** Apache License 2.0 — [LICENSE](LICENSE)
- **Dataset:** CC BY 4.0 — [LICENSE-DATASET](LICENSE-DATASET)

## Citação

```bibtex
@software{curupira2026,
  author = {Tavares, Rafael Machado},
  title  = {Curupira: benchmark de agentes de IA em português brasileiro},
  year   = {2026},
  url    = {https://github.com/rafaelmtavares44/curupira}
}
```

---

<div align="center">

*O Curupira é o protetor da floresta no folclore brasileiro. Anda com os pés
virados para trás, para que quem o persegue siga as pegadas na direção errada.*

*Bom nome para um projeto que caça a falha que a máquina esconde.*

</div>
