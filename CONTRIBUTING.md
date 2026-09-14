# Contribuindo com o Curupira

## Antes de qualquer coisa

```bash
pip install -e ".[dev]"
pre-commit install
```

Nada entra na `main` sem: `ruff check`, `ruff format --check`, `mypy` (strict),
`bandit`, `pip-audit` e `pytest` passando.

## Regras que não se negociam

1. **Nenhum dado de pessoa real.** Nenhum documento, CPF, CNPJ, foto, nome ou
   endereço copiado de alguém. Tudo sintético e gerado proceduralmente. PR que
   contenha dado real é fechado, não corrigido.

2. **Matchers e validadores são nomes registrados em Python.** O YAML das tarefas
   é declarativo. Se rodar o benchmark exigir `eval()`, o benchmark está errado.

3. **Toda garantia nova vem com o teste que a comprova, no mesmo PR.**
   Geradores e validadores exigem teste de propriedade (Hypothesis): todo valor
   válido gerado passa na validação; todo valor corrompido falha.

4. **Nunca edite uma tarefa em silêncio.** Mudou o conteúdo, sobe `task_version`.
   Se a tarefa está numa suíte congelada, a mudança vira errata — a suíte não
   muda um byte.

5. **Tarefas nascem em PT-BR.** O par em inglês é derivado do português, nunca o
   contrário. `generated_from: pt-BR` é dado auditável, não comentário.

6. **`parity: strict` significa strict.** Só o idioma muda. Na dúvida, é
   `localized`. Afrouxar isso dá um Delta maior e indefensável.

## Adicionando uma tarefa

1. Escreva o YAML em `tasks/<trilha>/`.
2. Preencha `parity_notes` explicando exatamente o que muda entre as versões.
3. Gere um `canary_guid` único.
4. Rode `curupira validate` (lint do dataset).
5. Tarefa nova **nunca** entra em suíte congelada. Vai para a próxima.

## Adicionando um adaptador de provedor

Leia a **ADR 0002** primeiro. Adaptadores são escritos à mão de propósito: o
benchmark precisa saber exatamente quais bytes foram enviados ao modelo, porque
uma camada de normalização vira variável de confusão na medição.

## Commits

Conventional Commits. Decisões de arquitetura viram ADR em `docs/adr/`.
