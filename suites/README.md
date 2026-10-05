# Suítes congeladas

Uma suíte lista `task_id` + `task_version` + `sha256` de cada tarefa, com
`frozen_at`. Toda rodada nomeia uma suíte: `curupira run --suite v0.1`.

**Regras:**

- A suíte **não muda um byte** depois de congelada.
- Tarefa nova nunca entra em suíte congelada; vai para a próxima.
- Comparar notas de suítes diferentes é erro explícito da ferramenta.
- Bug numa tarefa vira **errata** (`v0.1.errata.yaml`, append-only), não edição.
- Teto de errata: 5%. Passando disso, a suíte está morta — encerra-se e corta-se
  a próxima.

`delta_subset` lista explicitamente os `pair_id` que entram no cálculo do Delta
PT-BR. Ela é declarada, não derivada: a base do Delta é cota de autoria, não
o que sobrou.

## Suítes

| suíte | congelada em | tarefas | pares no Delta | famílias | nota |
|---|---|---|---|---|---|
| `v0.1` | 16/09/2026 | 4 | 2 | 1 | só o separador decimal (`money-*`); o Delta dela não tem BCa |
| `v0.2` | 05/10/2026 | 46 | 23 | 11 | T1, T2 e T4; validada por dois pilotos pagos (ADR 0013 e 0014) |

As quatro `money-*` estão nas duas: tarefa congelada não muda, então o hash é o
mesmo. O que a v0.2 acrescenta são as 42 tarefas do lote das Entregas 19 a 22.
