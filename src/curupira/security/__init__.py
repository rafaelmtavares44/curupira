"""Barreiras técnicas em torno das chaves de API. Ver SECURITY.md e ADR 0003.

Este é o único subpacote **implementado** na Fase 0, porque a garantia que ele
oferece precisa vir com o teste que a comprova — e o teste precisa existir desde
o primeiro commit, não depois do primeiro vazamento.
"""

from __future__ import annotations

from curupira.security.redaction import (
    MARCA_REDIGIDO,
    FiltroDeRedacao,
    FormatadorDeRedacao,
    carregar_chave,
    esquecer_segredos,
    instalar_redacao,
    redigir,
    registrar_segredo,
)

__all__ = [
    "MARCA_REDIGIDO",
    "FiltroDeRedacao",
    "FormatadorDeRedacao",
    "carregar_chave",
    "esquecer_segredos",
    "instalar_redacao",
    "redigir",
    "registrar_segredo",
]
