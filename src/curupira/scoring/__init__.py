"""Pontuação: camadas 1 a 4, da menos para a mais subjetiva.

1. **AST** — a chamada está sintática e semanticamente correta. Zero subjetividade.
2. **Execução** — rodou em sandbox e produziu o resultado esperado. Zero.
3. **Validador de formato** — dígito verificador, parser de data, regex. Zero.
4. **Juiz LLM** — SÓ para texto livre, SEMPRE calibrado contra anotação humana.

**Invariante que o agregador impõe:** nenhuma tarefa pontuada por juiz entra no
Delta PT-BR. A hipótese do projeto é que modelos degradam em português; um juiz
LLM avaliando português degrada pela mesma razão, e provavelmente de forma
assimétrica entre os idiomas. Usar juiz no Delta é medir a régua com a régua
torta.

Regra de desenho que economiza juiz: se o comportamento pode virar ação
observável no ambiente, **reescreva a tarefa** em vez de contratar um juiz.
"""

from __future__ import annotations
