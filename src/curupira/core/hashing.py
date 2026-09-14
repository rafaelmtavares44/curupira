"""Serialização canônica e hash de conteúdo de tarefa.

O hash é calculado sobre o **modelo Pydantic normalizado**, nunca sobre o texto
do YAML. Três consequências, todas desejadas:

1. Reidentação, ordem de chaves e comentários no YAML **não** mudam o hash. O
   dataset pode ser reformatado sem invalidar uma suíte congelada.
2. A forma curta (`calls:`) e a expansão canônica equivalente (`accept:` com o
   id e o racional que o carregador injeta) hasheiam **igual**, porque depois da
   carga são o mesmo objeto. Ver `curupira.core.loader`.
3. O conjunto de alternativas aceitáveis entra no hash. Descobrir um caminho
   válido esquecido **sobe `task_version`** — não é edição silenciosa.

Normalização Unicode NFC
------------------------
Toda string passa por NFC antes de serializar. Isso não é zelo excessivo num
dataset em português: "transferência" digitado no macOS chega em NFD (e + acento
combinante) e no Windows em NFC (e-acento como um ponto de código). São bytes
diferentes para o mesmo texto. Sem NFC, a mesma tarefa hashearia diferente
dependendo de onde foi editada, e a suíte congelada acusaria adulteração onde
houve apenas um `git checkout`.

O que NÃO é excluído
--------------------
Nada. O modelo inteiro entra, `parity_notes` inclusive. É uma escolha
conservadora com um custo real: corrigir um typo numa nota de paridade muda o
hash e obriga a subir `task_version`. Aceitamos o custo porque a alternativa —
manter uma lista de campos "não semânticos" — é uma lista que alguém vai
estender até ela cobrir algo que importava.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata

from curupira.core.task import Tarefa


def _normalizar(valor: object) -> object:
    """Aplica NFC recursivamente a toda string, em chave e em valor.

    Args:
        valor: qualquer fragmento já convertido para tipos JSON.

    Returns:
        O mesmo fragmento com as strings em NFC.
    """
    if isinstance(valor, str):
        return unicodedata.normalize("NFC", valor)
    if isinstance(valor, list):
        return [_normalizar(item) for item in valor]
    if isinstance(valor, dict):
        return {
            unicodedata.normalize("NFC", str(chave)): _normalizar(item)
            for chave, item in valor.items()
        }
    return valor


def bytes_canonicos(tarefa: Tarefa) -> bytes:
    """Serializa a tarefa de forma canônica e determinística.

    Chaves ordenadas, sem espaço supérfluo, strings em NFC, UTF-8. `NaN` e
    `Infinity` são recusados: não são JSON válido e destruiriam o determinismo.

    Args:
        tarefa: a tarefa a serializar.

    Returns:
        Os bytes canônicos.

    Raises:
        ValueError: se algum campo numérico for `NaN` ou infinito.
    """
    bruto = tarefa.model_dump(mode="json")
    texto = json.dumps(
        _normalizar(bruto),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return texto.encode("utf-8")


def hash_da_tarefa(tarefa: Tarefa) -> str:
    """Calcula o SHA-256 hexadecimal dos bytes canônicos da tarefa.

    Args:
        tarefa: a tarefa a hashear.

    Returns:
        Hash hexadecimal de 64 caracteres minúsculos.
    """
    return hashlib.sha256(bytes_canonicos(tarefa)).hexdigest()
