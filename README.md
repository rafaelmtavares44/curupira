# Curupira

**Benchmark de agentes de IA em português brasileiro.**

> O Curupira é o protetor da floresta no folclore brasileiro: anda com os pés
> virados para trás para confundir quem o persegue. Nome certo para um benchmark
> que caça a falha que o agente esconde.

[![CI](https://github.com/rafaelmtavares44/curupira/actions/workflows/ci.yml/badge.svg)](https://github.com/rafaelmtavares44/curupira/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![Código: Apache 2.0](https://img.shields.io/badge/c%C3%B3digo-Apache--2.0-green)
![Dataset: CC BY 4.0](https://img.shields.io/badge/dataset-CC--BY--4.0-green)

> **Status: Fase 0 — esqueleto.** O modelo de dados está definido e os módulos
> existem com assinatura e docstring. A implementação da v0.1 ainda não começou.
> Nada aqui produz nota ainda.

---

## O problema

O benchmark que mede agente não fala português; os que falam português não medem
agente.

| Benchmark | Mede agente? | Fala PT-BR? |
|---|---|---|
| BFCL V4 (Berkeley) | sim | não |
| CLARIN-PT-LDB (PROPOR 2026) | não | português europeu |
| Open PT LLM Leaderboard, PoETa v2, Prosa, LLM Fauna | não | sim |
| **Curupira** | **sim** | **sim** |

## A métrica-assinatura: Delta PT-BR

A mesma tarefa, a mesma ferramenta, a mesma dificuldade, rodada em inglês e em
português brasileiro. A diferença entre as notas é o **Delta PT-BR**: o custo, em
pontos, de falar português com o seu agente.

O Delta é calculado **exclusivamente** sobre pares marcados `parity: strict`, e
**nunca** sobre tarefas pontuadas por juiz LLM — um juiz LLM avaliando português
degrada pela mesma razão que estamos tentando medir.

## O que o Curupira não é

- **Não** é o BFCL traduzido. As tarefas nascem em PT-BR; o par em inglês é
  derivado delas.
- **Não** é benchmark de conhecimento. Não pergunta fatos; mede execução.
- **Não** é leaderboard de modelo, e sim de **agente**: modelo + framework +
  prompt + tools. Trocar CrewAI por LangGraph muda a nota, e essa informação é o
  produto.

## Trilhas

| | Trilha | Foco |
|---|---|---|
| T1 | Tool calling em PT-BR | simples, múltiplas, paralelas, multi-turno, detecção de irrelevância |
| T2 | Formatos brasileiros | `1.234,56`, `dd/mm/aaaa`, CPF, CNPJ (inclusive alfanumérico), CEP, PIX, boleto, NF-e |
| T3 | Documentos brasileiros | nota fiscal, boleto, contracheque, conta de luz, edital — todos sintéticos |
| T4 | Português real | WhatsApp sem acento, abreviação, regionalismo, pedido incompleto |
| T5 | Segurança em português | prompt injection em PT-BR; recusa que funciona em inglês e vaza em português |
| T6 | Multi-turno com efeito colateral | o agente confirma antes de ação destrutiva? |

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

## Lockfile com hash (pendente)

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

## Portão de qualidade

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
  core/        modelo de dados: tarefa, expect, resultado, suite, hash, registro
  formatos/    CPF, CNPJ, CEP, telefone, placa, PIX, boleto, NF-e
               (validar / gerar / corromper, com teste de propriedade)
  matchers/    matchers registrados por nome, usados pelo AST checker
  scoring/     AST checker, classificação de falha silenciosa, taxonomia
  adapters/    um adaptador por provedor, escrito à mão (ADR 0002)
  runner/      execução e cache de resposta
  report/      agregação, Delta PT-BR, linhas de base triviais
  security/    redação de segredos (implementado — ver tests/test_segredos.py)
tasks/         o dataset, em YAML, declarativo e auditável por humano
suites/        suítes congeladas e erratas
docs/adr/      decisões registradas
```

## Princípio de arquitetura

**Guarde o bruto, agregue tarde.** O pipeline separa três etapas, cada uma
re-executável a partir do disco:

```
executar  ->  runs/<id>/raw.jsonl      (resposta crua, argumentos exatos)
pontuar   ->  runs/<id>/scored.parquet (verdicto por repetição)
agregar   ->  runs/<id>/report.json    (acurácia, Delta, falha silenciosa)
```

Rotular um modo de falha novo, aplicar uma errata ou corrigir um matcher não
exige rerodar nada — só reprocessar o bruto.

## Ética e dados

Nenhum documento, CPF, CNPJ ou dado de pessoa real entra no dataset, em hipótese
alguma. Tudo é sintético e gerado proceduralmente, a partir dos algoritmos
públicos de formação e dígito verificador.

**Declaramos deliberadamente que não verificamos os identificadores gerados
contra nenhuma base real**, porque fazê-lo exigiria tratar dados pessoais reais
de milhões de pessoas para proteger um dataset que não contém nenhum.

Procedimento de colisão: ver [SECURITY.md](SECURITY.md).

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
