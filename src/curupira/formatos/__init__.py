"""Identificadores brasileiros: validar, gerar e corromper de forma controlada.

Três regras valem para todos os módulos deste subpacote:

1. **Toda função de geração recebe um `random.Random` semeado** a partir do
   `task_id`. O dataset é regenerável a partir das seeds mais a versão do
   gerador, e um job de CI confere a regeneração contra os hashes da suíte.
2. **A corrupção é declarada, nunca descoberta.** `corromper(v, modo)` devolve um
   valor que o validador reprova por aquele motivo.
3. **Teste de propriedade obrigatório** (Hypothesis): todo valor válido gerado
   passa na validação; todo valor corrompido falha. `SEQUENCIA_REPETIDA` e
   `MASCARA_ERRADA` são os dois casos que quebram implementação ingênua — o
   primeiro passa na aritmética do módulo 11, o segundo só falha se o validador
   checar formato. São, por isso, os testes que valem alguma coisa.

**Ética, inegociável:** nada aqui copia dado de ninguém. Tudo é produzido pelos
algoritmos públicos de formação e dígito verificador. Ver SECURITY.md para o
procedimento de colisão e para a razão de NÃO verificarmos contra base real.
"""

from __future__ import annotations
