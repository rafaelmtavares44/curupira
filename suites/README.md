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

*(Nenhuma suíte congelada ainda. A v0.1 é congelada quando T1 e T2 fecharem.)*
