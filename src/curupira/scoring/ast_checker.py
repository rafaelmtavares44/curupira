"""O AST checker: casa a saída do agente contra o conjunto de alternativas.

Algoritmo:

1. Normaliza a saída do agente — ordem de chaves, whitespace, unicode NFC,
   números. A ordem dos argumentos nunca importa, porque `args` é dicionário;
   o que importa é normalizar antes de comparar.
2. Para cada alternativa, em ordem de `preference_rank` e depois de índice:
   - `call_order == "strict"`: compara posicionalmente.
   - `call_order == "any"`: emparelhamento bipartido entre N chamadas esperadas e
     M observadas. Com N menor ou igual a 5, **enumeração exaustiva das
     permutações** (no máximo 120), que é determinística e trivial. Acima disso,
     algoritmo húngaro.
   - N diferente de M falha imediatamente: chamada faltando ou sobrando.
3. A primeira alternativa que passa vence. Grava `matched_accept_id` e
   `preference_rank` no resultado.

**Não use emparelhamento guloso.** Guloso dá resultado dependente da ordem de
iteração, e resultado dependente de ordem num benchmark é bug, não detalhe.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from curupira.core.expect import Alternativa, EsperaChamadaDeFerramenta
from curupira.core.result import ChamadaObservada


class VeredictoAst(BaseModel):
    """O que o AST checker concluiu, com a trilha de auditoria."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passou: bool
    matched_accept_id: str | None = None
    preference_rank: int | None = None
    motivo: str
    """Por que falhou, quando falhou. Entra no relatório de diagnóstico."""


def normalizar_chamadas(chamadas: tuple[ChamadaObservada, ...]) -> tuple[ChamadaObservada, ...]:
    """Normaliza chamadas observadas antes da comparação.

    Args:
        chamadas: as chamadas como o modelo as emitiu.

    Returns:
        As chamadas normalizadas.
    """
    raise NotImplementedError


def casar_alternativa(
    alternativa: Alternativa, observadas: tuple[ChamadaObservada, ...]
) -> VeredictoAst:
    """Tenta casar uma única alternativa contra as chamadas observadas.

    Args:
        alternativa: o caminho candidato.
        observadas: as chamadas normalizadas do agente.

    Returns:
        O veredicto para esta alternativa.
    """
    raise NotImplementedError


def checar(
    espera: EsperaChamadaDeFerramenta, observadas: tuple[ChamadaObservada, ...]
) -> VeredictoAst:
    """Casa a saída do agente contra o conjunto inteiro de alternativas.

    Args:
        espera: o bloco `expect` da tarefa.
        observadas: as chamadas que o agente emitiu.

    Returns:
        O veredicto, com o id da alternativa que casou quando passou.
    """
    raise NotImplementedError
