"""Execução de uma rodada: três etapas separadas e re-executáveis.

```
executar  ->  runs/<id>/raw.jsonl       (resposta crua, argumentos exatos)
pontuar   ->  runs/<id>/scored.parquet  (veredicto por repetição)
agregar   ->  runs/<id>/report.json     (acurácia, Delta, falha silenciosa)
```

A separação é o que torna P1 e P3 baratos: rotular um modo de falha novo, aplicar
uma errata ou corrigir um matcher reprocessa o bruto em segundos, sem gastar um
centavo de API.
"""

from __future__ import annotations
