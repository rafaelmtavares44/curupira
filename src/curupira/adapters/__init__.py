"""Adaptadores de provedor, escritos à mão. Ver ADR 0002.

O argumento decisivo contra uma camada pronta não é segurança, é medição: o
Curupira mede como um agente se comporta diante de uma definição de ferramenta
específica, e uma camada que normaliza schemas entre provedores altera os bytes
que chegam ao modelo de forma diferente por provedor. Parte do Delta passaria a
medir a camada, não o agente.

O incidente do `litellm` em 24/03/2026 é o segundo argumento, não o primeiro.
"""

from __future__ import annotations
