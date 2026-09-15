"""O AST checker: o coração da camada de pontuação sem subjetividade."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from typing import Any

import pytest

from curupira.core.expect import EsperaChamadaDeFerramenta
from curupira.core.registry import limpar_registro
from curupira.core.result import ChamadaObservada
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.scoring.ast_checker import (
    MAXIMO_DE_CHAMADAS_PERMUTAVEIS,
    checar,
    normalizar_chamadas,
)


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


def _espera(**overrides: Any) -> EsperaChamadaDeFerramenta:
    base: dict[str, Any] = {
        "kind": "tool_call",
        "accept": [
            {
                "id": "canonica",
                "rationale": "caminho direto",
                "calls": [
                    {
                        "name": "criar_transferencia",
                        "args": {"valor_centavos": 123456, "favorecido": "Silva"},
                        "arg_specs": {
                            "valor_centavos": {"matcher": "exact_int"},
                            "favorecido": {"matcher": "fuzzy_name"},
                        },
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return EsperaChamadaDeFerramenta.model_validate(base)


def _chamada(nome: str = "criar_transferencia", **args: Any) -> ChamadaObservada:
    padrao: dict[str, Any] = {"valor_centavos": 123456, "favorecido": "Silva"}
    padrao.update(args)
    return ChamadaObservada(name=nome, args=padrao)


# --------------------------------------------------------------------------
# Casos basicos
# --------------------------------------------------------------------------


def test_chamada_correta_passa() -> None:
    veredicto = checar(_espera(), (_chamada(),))
    assert veredicto.passou
    assert veredicto.matched_accept_id == "canonica"
    assert veredicto.preference_rank == 0


def test_o_erro_de_mil_vezes_e_reprovado() -> None:
    """A armadilha do separador decimal, de ponta a ponta."""
    veredicto = checar(_espera(), (_chamada(valor_centavos=123456000),))
    assert not veredicto.passou
    assert "valor_centavos" in veredicto.motivo


def test_ferramenta_errada() -> None:
    veredicto = checar(_espera(), (_chamada(nome="listar_transferencias"),))
    assert not veredicto.passou
    assert "listar_transferencias" in veredicto.motivo


def test_nenhuma_chamada_quando_se_esperava_uma() -> None:
    veredicto = checar(_espera(), ())
    assert not veredicto.passou
    assert "o agente fez 0" in veredicto.motivo


def test_chamada_a_mais() -> None:
    veredicto = checar(_espera(), (_chamada(), _chamada()))
    assert not veredicto.passou


def test_argumento_faltando() -> None:
    veredicto = checar(_espera(), (ChamadaObservada(name="criar_transferencia", args={}),))
    assert not veredicto.passou
    assert "obrigatorio" in veredicto.motivo


def test_argumento_inventado_e_rejeitado_por_padrao() -> None:
    veredicto = checar(_espera(), (_chamada(moeda="BRL"),))
    assert not veredicto.passou
    assert "nao esperados" in veredicto.motivo


def test_argumento_extra_pode_ser_ignorado() -> None:
    espera = _espera()
    bruto = espera.model_dump()
    bruto["accept"][0]["calls"][0]["extra_args"] = "ignore"
    veredicto = checar(EsperaChamadaDeFerramenta.model_validate(bruto), (_chamada(moeda="BRL"),))
    assert veredicto.passou


# --------------------------------------------------------------------------
# Politicas de argumento
# --------------------------------------------------------------------------


def _com_politica(politica: str) -> EsperaChamadaDeFerramenta:
    espera = _espera()
    bruto = espera.model_dump()
    specs = bruto["accept"][0]["calls"][0]["arg_specs"]
    specs["favorecido"]["policy"] = politica
    return EsperaChamadaDeFerramenta.model_validate(bruto)


def test_argumento_opcional_pode_faltar() -> None:
    observada = ChamadaObservada(name="criar_transferencia", args={"valor_centavos": 123456})
    assert checar(_com_politica("optional"), (observada,)).passou


def test_argumento_opcional_presente_ainda_e_conferido() -> None:
    assert not checar(_com_politica("optional"), (_chamada(favorecido="Pereira"),)).passou


def test_argumento_proibido() -> None:
    """Contra o agente que inventa campo que a ferramenta não pediu."""
    veredicto = checar(_com_politica("forbidden"), (_chamada(),))
    assert not veredicto.passou
    assert "proibido" in veredicto.motivo


# --------------------------------------------------------------------------
# Alternativas
# --------------------------------------------------------------------------


def _com_alternativa() -> EsperaChamadaDeFerramenta:
    espera = _espera()
    bruto = espera.model_dump()
    bruto["accept"] = [*bruto["accept"]]
    bruto["accept"].append(
        {
            "id": "consulta_antes",
            "rationale": "consultar o favorecido antes de transferir tambem esta certo",
            "preference_rank": 1,
            "call_order": "strict",
            "calls": [
                {
                    "name": "consultar_favorecido",
                    "args": {"nome": "Silva"},
                    "arg_specs": {"nome": {"matcher": "fuzzy_name"}},
                },
                {
                    "name": "criar_transferencia",
                    "args": {"valor_centavos": 123456, "favorecido": "Silva"},
                    "arg_specs": {
                        "valor_centavos": {"matcher": "exact_int"},
                        "favorecido": {"matcher": "fuzzy_name"},
                    },
                },
            ],
        }
    )
    return EsperaChamadaDeFerramenta.model_validate(bruto)


def test_caminho_alternativo_tambem_passa() -> None:
    """Um agente competente que consulta antes de agir não pode ser reprovado."""
    observadas = (
        ChamadaObservada(name="consultar_favorecido", args={"nome": "Silva"}),
        _chamada(),
    )
    veredicto = checar(_com_alternativa(), observadas)
    assert veredicto.passou
    assert veredicto.matched_accept_id == "consulta_antes"
    assert veredicto.preference_rank == 1


def test_a_alternativa_preferida_vence() -> None:
    veredicto = checar(_com_alternativa(), (_chamada(),))
    assert veredicto.matched_accept_id == "canonica"


def test_motivo_reune_todas_as_alternativas() -> None:
    """Falhar em silêncio sobre qual caminho foi tentado é diagnóstico inútil."""
    veredicto = checar(_com_alternativa(), (_chamada(valor_centavos=1),))
    assert not veredicto.passou
    assert "[canonica]" in veredicto.motivo
    assert "[consulta_antes]" in veredicto.motivo


# --------------------------------------------------------------------------
# Ordem das chamadas
# --------------------------------------------------------------------------


def _paralelas(ordem: str) -> EsperaChamadaDeFerramenta:
    return EsperaChamadaDeFerramenta.model_validate(
        {
            "kind": "tool_call",
            "accept": [
                {
                    "id": "canonica",
                    "rationale": "duas transferencias independentes",
                    "call_order": ordem,
                    "calls": [
                        {"name": "criar_transferencia", "args": {"favorecido": "Silva"}},
                        {"name": "criar_transferencia", "args": {"favorecido": "Souza"}},
                    ],
                }
            ],
        }
    )


def test_ordem_qualquer_aceita_as_duas_ordens() -> None:
    a = ChamadaObservada(name="criar_transferencia", args={"favorecido": "Silva"})
    b = ChamadaObservada(name="criar_transferencia", args={"favorecido": "Souza"})
    assert checar(_paralelas("any"), (a, b)).passou
    assert checar(_paralelas("any"), (b, a)).passou


def test_ordem_estrita_reprova_a_ordem_invertida() -> None:
    a = ChamadaObservada(name="criar_transferencia", args={"favorecido": "Silva"})
    b = ChamadaObservada(name="criar_transferencia", args={"favorecido": "Souza"})
    assert checar(_paralelas("strict"), (a, b)).passou
    assert not checar(_paralelas("strict"), (b, a)).passou


def test_muitas_chamadas_com_ordem_qualquer_estoura() -> None:
    """Degradar para emparelhamento guloso daria resultado dependente de ordem.

    Num benchmark isso é bug: a mesma resposta passaria ou falharia conforme a
    ordem em que o modelo emitiu as chamadas. Melhor estourar e a tarefa ser
    redesenhada.
    """
    n = MAXIMO_DE_CHAMADAS_PERMUTAVEIS + 1
    chamadas = [{"name": "f", "args": {"i": i}} for i in range(n)]
    espera = EsperaChamadaDeFerramenta.model_validate(
        {
            "kind": "tool_call",
            "accept": [{"id": "c", "rationale": "r", "call_order": "any", "calls": chamadas}],
        }
    )
    observadas = tuple(ChamadaObservada(name="f", args={"i": i}) for i in range(n))
    with pytest.raises(ValueError, match="enumeracao exaustiva"):
        checar(espera, observadas)


# --------------------------------------------------------------------------
# Determinismo e normalizacao
# --------------------------------------------------------------------------


def test_resultado_nao_depende_da_ordem_de_iteracao() -> None:
    """Duas execuções sobre a mesma resposta devolvem sempre o mesmo veredicto."""
    espera = _com_alternativa()
    observadas = (
        ChamadaObservada(name="consultar_favorecido", args={"nome": "Silva"}),
        _chamada(),
    )
    vereditos = [checar(espera, observadas) for _ in range(5)]
    assert all(v == vereditos[0] for v in vereditos)


def test_normalizacao_aplica_nfc_e_colapsa_espacos() -> None:
    decomposto = unicodedata.normalize("NFD", "José")
    chamada = ChamadaObservada(name="  f  ", args={"nome": f"  {decomposto}  "})
    (normalizada,) = normalizar_chamadas((chamada,))
    assert normalizada.name == "f"
    assert normalizada.args["nome"] == "José"


def test_normalizacao_preserva_raw_arguments() -> None:
    """`raw_arguments` é o registro do que o modelo emitiu — rotula a falha."""
    chamada = ChamadaObservada(name="f", args={"v": 1}, raw_arguments='{"v": "1.234,56"}')
    (normalizada,) = normalizar_chamadas((chamada,))
    assert normalizada.raw_arguments == '{"v": "1.234,56"}'


def test_argumento_sem_spec_usa_igualdade_estrita() -> None:
    espera = EsperaChamadaDeFerramenta.model_validate(
        {
            "kind": "tool_call",
            "accept": [
                {
                    "id": "c",
                    "rationale": "r",
                    "calls": [{"name": "f", "args": {"x": 1}}],
                }
            ],
        }
    )
    assert checar(espera, (ChamadaObservada(name="f", args={"x": 1}),)).passou
    assert not checar(espera, (ChamadaObservada(name="f", args={"x": "1"}),)).passou


def test_normalizacao_desce_em_lista_e_dicionario() -> None:
    """Argumento aninhado também é normalizado: modelo manda objeto o tempo todo."""
    decomposto = unicodedata.normalize("NFD", "José")
    chamada = ChamadaObservada(
        name="f",
        args={"lista": [f" {decomposto} ", 1], "objeto": {f" {decomposto} ": " Silva "}},
    )
    (n,) = normalizar_chamadas((chamada,))
    assert n.args["lista"] == ["José", 1]
    assert n.args["objeto"] == {"José": "Silva"}


def test_argumento_proibido_ausente_passa() -> None:
    """Proibido significa "não pode vir", não "tem que vir"."""
    observada = ChamadaObservada(name="criar_transferencia", args={"valor_centavos": 123456})
    assert checar(_com_politica("forbidden"), (observada,)).passou
