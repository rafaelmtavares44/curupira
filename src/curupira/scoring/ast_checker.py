"""O AST checker: casa a saída do agente contra o conjunto de alternativas.

Algoritmo:

1. Normaliza a saída do agente — unicode NFC nas strings, espaços colapsados. A
   ordem dos argumentos nunca importa, porque `args` é dicionário; o que importa
   é normalizar antes de comparar.
2. Para cada alternativa, em ordem de `preference_rank` e depois de índice:
   - `call_order == "strict"`: compara posicionalmente.
   - `call_order == "any"`: **enumeração exaustiva das permutações** das chamadas
     observadas contra as esperadas.
   - N diferente de M falha imediatamente: chamada faltando ou sobrando.
3. A primeira alternativa que passa vence. Grava `matched_accept_id` e
   `preference_rank` no resultado.

**Não use emparelhamento guloso.** Guloso dá resultado dependente da ordem de
iteração, e resultado dependente de ordem num benchmark é bug, não detalhe: a
mesma resposta poderia passar ou falhar conforme a ordem em que o modelo emitiu
as chamadas. Com N ≤ 6 a enumeração exaustiva custa no máximo 720 comparações,
que é ruído perto de uma chamada de API.
"""

from __future__ import annotations

from itertools import permutations
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from curupira.core.enums import (
    OrdemDeChamadas,
    PoliticaDeArgumento,
    PoliticaDeArgumentoExtra,
)
from curupira.core.expect import (
    Alternativa,
    ChamadaEsperada,
    EspecificacaoDeArgumento,
    EsperaChamadaDeFerramenta,
)
from curupira.core.registry import obter_matcher
from curupira.core.result import ChamadaObservada
from curupira.matchers.texto import normalizar

MAXIMO_DE_CHAMADAS_PERMUTAVEIS: Final = 6
"""Acima disso a enumeracao exaustiva deixa de ser trivial (720 permutacoes).

Nenhuma tarefa realista do benchmark chega perto. Se chegar, o problema e o
desenho da tarefa, nao o algoritmo — por isso estoura em vez de degradar para um
emparelhamento guloso que daria resultado dependente de ordem.
"""


class VeredictoAst(BaseModel):
    """O que o AST checker concluiu, com a trilha de auditoria."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passou: bool
    matched_accept_id: str | None = None
    preference_rank: int | None = None
    motivo: str
    """Por que falhou, quando falhou. Entra no relatorio de diagnostico."""


def _normalizar_valor(valor: JsonValue) -> JsonValue:
    if isinstance(valor, str):
        return normalizar(valor)
    if isinstance(valor, list):
        return [_normalizar_valor(v) for v in valor]
    if isinstance(valor, dict):
        return {normalizar(k): _normalizar_valor(v) for k, v in valor.items()}
    return valor


def normalizar_chamadas(chamadas: tuple[ChamadaObservada, ...]) -> tuple[ChamadaObservada, ...]:
    """Normaliza chamadas observadas antes da comparação.

    `raw_arguments` é preservado intacto: ele é o registro do que o modelo
    realmente emitiu, e um `"1.234,56"` cru é o dado que rotula a falha silenciosa.

    Args:
        chamadas: as chamadas como o modelo as emitiu.

    Returns:
        As chamadas normalizadas.
    """
    return tuple(
        chamada.model_copy(
            update={
                "name": normalizar(chamada.name),
                "args": {normalizar(k): _normalizar_valor(v) for k, v in chamada.args.items()},
            }
        )
        for chamada in chamadas
    )


def _casa_argumento(
    spec: EspecificacaoDeArgumento | None,
    observado: JsonValue,
    esperado: JsonValue,
) -> bool:
    """Compara um argumento presente, usando o matcher declarado."""
    if spec is None:
        return observado == esperado
    return obter_matcher(spec.matcher)(observado, esperado, spec.params)


def _motivo_da_falha(esperada: ChamadaEsperada, observada: ChamadaObservada) -> str | None:
    """Compara uma chamada esperada com uma observada.

    Returns:
        `None` se casou; caso contrário, a razão da falha.
    """
    if esperada.name != observada.name:
        return f"esperava a ferramenta '{esperada.name}', veio '{observada.name}'"

    nomes = set(esperada.args) | set(esperada.arg_specs)
    for nome in sorted(nomes):
        spec = esperada.arg_specs.get(nome)
        politica = spec.policy if spec else PoliticaDeArgumento.OBRIGATORIO
        presente = nome in observada.args

        if politica is PoliticaDeArgumento.PROIBIDO:
            if presente:
                return f"o argumento '{nome}' e proibido nesta chamada e foi enviado"
            continue
        if not presente:
            if politica is PoliticaDeArgumento.OPCIONAL:
                continue
            return f"falta o argumento obrigatorio '{nome}'"
        if not _casa_argumento(spec, observada.args[nome], esperada.args.get(nome)):
            return (
                f"o argumento '{nome}' nao casou: veio {observada.args[nome]!r}, "
                f"esperado {esperada.args.get(nome)!r}"
            )

    if esperada.extra_args is PoliticaDeArgumentoExtra.REJEITAR:
        sobrando = sorted(set(observada.args) - nomes)
        if sobrando:
            return f"argumentos nao esperados: {sobrando}"
    return None


def _casa_em_alguma_ordem(
    esperadas: tuple[ChamadaEsperada, ...], observadas: tuple[ChamadaObservada, ...]
) -> str | None:
    """Tenta casar N esperadas contra N observadas em qualquer ordem.

    Raises:
        ValueError: se houver chamadas demais para enumerar as permutações.
    """
    if len(esperadas) > MAXIMO_DE_CHAMADAS_PERMUTAVEIS:
        msg = (
            f"tarefa com {len(esperadas)} chamadas e call_order=any: acima de "
            f"{MAXIMO_DE_CHAMADAS_PERMUTAVEIS} a enumeracao exaustiva sai de mao. "
            "Divida a tarefa ou declare call_order=strict."
        )
        raise ValueError(msg)

    ultimo_motivo = "nenhuma ordem das chamadas observadas casou com a esperada"
    for ordem in permutations(observadas):
        motivos = [
            _motivo_da_falha(esperada, observada)
            for esperada, observada in zip(esperadas, ordem, strict=True)
        ]
        if all(m is None for m in motivos):
            return None
        primeiro = next((m for m in motivos if m is not None), None)
        if primeiro is not None:
            ultimo_motivo = primeiro
    return ultimo_motivo


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
    esperadas = alternativa.calls
    if len(esperadas) != len(observadas):
        return VeredictoAst(
            passou=False,
            motivo=(f"esperava {len(esperadas)} chamada(s), o agente fez {len(observadas)}"),
        )

    if alternativa.call_order is OrdemDeChamadas.ESTRITA:
        motivos = [
            _motivo_da_falha(esperada, observada)
            for esperada, observada in zip(esperadas, observadas, strict=True)
        ]
        motivo = next((m for m in motivos if m is not None), None)
    else:
        motivo = _casa_em_alguma_ordem(esperadas, observadas)

    if motivo is not None:
        return VeredictoAst(passou=False, motivo=motivo)
    return VeredictoAst(
        passou=True,
        matched_accept_id=alternativa.id,
        preference_rank=alternativa.preference_rank,
        motivo="casou",
    )


def checar(
    espera: EsperaChamadaDeFerramenta, observadas: tuple[ChamadaObservada, ...]
) -> VeredictoAst:
    """Casa a saída do agente contra o conjunto inteiro de alternativas.

    A ordem de tentativa é `(preference_rank, indice)`, estável: duas execuções
    sobre a mesma resposta devolvem sempre a mesma alternativa. Num benchmark,
    resultado dependente de ordem de iteração é bug.

    Args:
        espera: o bloco `expect` da tarefa.
        observadas: as chamadas que o agente emitiu.

    Returns:
        O veredicto, com o id da alternativa que casou quando passou. Quando
        falha, o motivo é o da alternativa mais preferida — a que o autor da
        tarefa considera o caminho ideal.
    """
    normalizadas = normalizar_chamadas(observadas)
    ordenadas = sorted(enumerate(espera.accept), key=lambda par: (par[1].preference_rank, par[0]))
    motivos: list[str] = []
    for _, alternativa in ordenadas:
        veredicto = casar_alternativa(alternativa, normalizadas)
        if veredicto.passou:
            return veredicto
        motivos.append(f"[{alternativa.id}] {veredicto.motivo}")
    return VeredictoAst(passou=False, motivo=" | ".join(motivos))
