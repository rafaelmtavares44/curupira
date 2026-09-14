"""Curupira — benchmark de agentes de IA em português brasileiro.

O produto deste pacote não é código: é um número defensável. Três princípios
atravessam o desenho e explicam quase toda decisão que parece excessiva:

1. **Guarde o bruto, agregue tarde.** Executar, pontuar e agregar são três etapas
   distintas, cada uma re-executável a partir do disco. Rotular um modo de falha
   novo ou aplicar uma errata nunca exige rerodar o benchmark.
2. **Nenhuma subjetividade onde um validador serve.** Juiz LLM só toca texto
   livre, e **nunca** entra no cálculo do Delta PT-BR — um juiz em português
   degrada pela mesma razão que estamos medindo.
3. **Quem tem chave não executa; quem executa não tem chave.** (ADR 0003.)
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

SCHEMA_VERSION = 1
"""Versão do schema de tarefa. Sobe só em mudança incompatível do formato."""

__all__ = ["SCHEMA_VERSION", "__version__"]
