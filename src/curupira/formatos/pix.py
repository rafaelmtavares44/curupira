"""As cinco formas de chave PIX.

CPF, CNPJ, e-mail, telefone em E.164 e chave aleatória (EVP), que é um UUID
versão 4. Cada tipo delega ao validador correspondente.

Os formatos vêm do schema oficial do DICT (`bacen/pix-dict-api`), não de
intuição:

| Tipo | Regra |
|---|---|
| CPF | `^[0-9]{11}$` — **sem pontuação** |
| CNPJ | 14 caracteres, sem pontuação |
| Telefone | E.164, com o sinal de mais na frente |
| E-mail | minúsculo, no máximo 77 caracteres |
| EVP | UUID, gerado pelo DICT |

**Armadilha de alto valor:** pedir ao agente que "gere uma chave aleatória" e
verificar se o UUID produzido é de fato versão 4 — nibble de versão igual a 4 e
bits de variante `10xx`, ou seja, o 17º caractere em `8 9 a b`. Um UUID v1 passa
por aleatório para quem não olha, e carrega timestamp e endereço MAC.

Segunda armadilha, mais sutil: a chave de CPF e a de CNPJ são **sem pontuação**.
`123.456.789-09` é um CPF válido e uma chave PIX inválida. Modelos erram isso com
frequência porque a pontuação é o formato "bonito" que aparece em documento.

Tensão declarada: CNPJ alfanumérico
-----------------------------------
O schema publicado do DICT descreve CNPJ como 14 **dígitos**. O CNPJ alfanumérico
entrou em vigor em julho de 2026, e a especificação do PIX ainda não refletia a
mudança quando este módulo foi escrito. Aceitamos as duas formas e registramos a
divergência: uma chave PIX de CNPJ alfanumérico é um caso em que a norma e a
implementação de mercado podem discordar — material de tarefa e de artigo, não
bug deste módulo.
"""

from __future__ import annotations

import re
import string
import uuid
from enum import StrEnum
from typing import Final

from curupira.core.enums import Corrupcao
from curupira.formatos import cnpj as mod_cnpj
from curupira.formatos import cpf as mod_cpf
from curupira.formatos import telefone as mod_telefone
from curupira.formatos.base import Gerado, rng_de

TAMANHO_MAXIMO_DE_EMAIL: Final = 77
"""Limite do DICT. Fonte: schema oficial do `bacen/pix-dict-api`."""

VERSAO_ALEATORIA: Final = 4
VARIANTE_RFC4122: Final = "89ab"
"""O 17º caractere de um UUID v4. Fora disso, a variante nao e a da RFC 4122."""

_EMAIL: Final = re.compile(
    r"^[a-z0-9.!#$&'*+/=?^_`{|}~-]+"
    r"@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_TELEFONE_E164: Final = re.compile(r"^\+[1-9][0-9]\d{1,14}$")
_UUID: Final = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SO_DIGITOS: Final = re.compile(r"^\d+$")

_DOMINIOS: Final = ("exemplo.com.br", "teste.org.br", "dominio-ficticio.net")
"""Dominios reservados para exemplo. Nenhum pertence a alguem de verdade."""


class TipoDeChavePix(StrEnum):
    """Os cinco tipos de chave PIX."""

    CPF = "cpf"
    CNPJ = "cnpj"
    EMAIL = "email"
    TELEFONE = "telefone"
    ALEATORIA = "aleatoria"


def _e_aleatoria(valor: str) -> bool:
    """Valida um EVP: formato de UUID, versão 4 e variante da RFC 4122.

    As duas verificações são necessárias e nenhuma basta sozinha. A versão separa
    o v4 do v1 — que carrega timestamp e endereço MAC, e portanto não é aleatório
    coisa nenhuma. A variante separa o UUID da RFC 4122 dos layouts legados da
    Microsoft, que casam o mesmo formato textual.
    """
    if not _UUID.match(valor):
        return False
    identificador = uuid.UUID(valor)
    return identificador.version == VERSAO_ALEATORIA and identificador.variant == uuid.RFC_4122


def _e_email(valor: str) -> bool:
    """Valida um e-mail como chave: minúsculo e dentro do limite do DICT."""
    return (
        len(valor) <= TAMANHO_MAXIMO_DE_EMAIL
        and valor == valor.lower()
        and bool(_EMAIL.match(valor))
    )


def _e_telefone(valor: str) -> bool:
    """Valida um telefone como chave: E.164, e brasileiro passa pelo módulo próprio."""
    if not _TELEFONE_E164.match(valor):
        return False
    if valor.startswith("+55"):
        return mod_telefone.validar(valor)
    return True


def detectar_tipo(valor: str) -> TipoDeChavePix | None:
    """Infere o tipo de uma chave PIX pelo formato.

    A inferência é **sem ambiguidade** porque os cinco espaços não se cruzam: o
    telefone exige `+`, o e-mail exige `@`, o EVP tem hífens em posições fixas, e
    CPF e CNPJ se distinguem pelo tamanho. Um valor que case dois tipos seria bug
    de especificação, não de implementação.

    Args:
        valor: a chave.

    Returns:
        O tipo, ou `None` se não casar com nenhum.
    """
    if valor.startswith("+"):
        return TipoDeChavePix.TELEFONE if _e_telefone(valor) else None
    if "@" in valor:
        return TipoDeChavePix.EMAIL if _e_email(valor) else None
    if "-" in valor:
        return TipoDeChavePix.ALEATORIA if _e_aleatoria(valor) else None
    if len(valor) == mod_cpf.TAMANHO and _SO_DIGITOS.match(valor):
        return TipoDeChavePix.CPF if mod_cpf.validar(valor) else None
    if len(valor) == mod_cnpj.TAMANHO:
        return TipoDeChavePix.CNPJ if mod_cnpj.validar(valor) else None
    return None


def validar_como(valor: str, tipo: TipoDeChavePix) -> bool:
    """Valida uma chave PIX forçando um tipo específico.

    Args:
        valor: a chave.
        tipo: o tipo a assumir.

    Returns:
        `True` se a chave é válida para esse tipo.
    """
    if tipo is TipoDeChavePix.CPF:
        return bool(_SO_DIGITOS.match(valor)) and mod_cpf.validar(valor)
    if tipo is TipoDeChavePix.CNPJ:
        return len(valor) == mod_cnpj.TAMANHO and mod_cnpj.validar(valor)
    if tipo is TipoDeChavePix.EMAIL:
        return _e_email(valor)
    if tipo is TipoDeChavePix.TELEFONE:
        return _e_telefone(valor)
    return _e_aleatoria(valor)


def validar(valor: str) -> bool:
    """Valida uma chave PIX, inferindo o tipo pelo formato.

    A chave de CPF e a de CNPJ são **sem pontuação** — uma chave mascarada é
    inválida, e esse é um erro que modelos cometem com frequência.

    Args:
        valor: a chave.

    Returns:
        `True` se a chave é válida para algum dos cinco tipos.
    """
    return detectar_tipo(valor) is not None


def gerar(rng_seed: int, tipo: TipoDeChavePix) -> Gerado:
    """Gera uma chave PIX válida do tipo pedido.

    O EVP é montado a partir de 16 bytes do gerador semeado e recebe os bits de
    versão e variante à mão. Usar `uuid.uuid4()` daria um UUID legítimo e
    **irreprodutível**, o que quebraria a regeneração do dataset a partir da seed.

    Args:
        rng_seed: a seed.
        tipo: o tipo de chave.

    Returns:
        A chave gerada.
    """
    rng = rng_de(rng_seed)
    if tipo is TipoDeChavePix.CPF:
        valor = mod_cpf.gerar(rng_seed).valor
    elif tipo is TipoDeChavePix.CNPJ:
        valor = mod_cnpj.gerar(rng_seed).valor
    elif tipo is TipoDeChavePix.TELEFONE:
        valor = mod_telefone.gerar(rng_seed, formato_e164=True).valor
    elif tipo is TipoDeChavePix.EMAIL:
        usuario = "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(5, 10)))
        valor = f"{usuario}@{rng.choice(_DOMINIOS)}"
    else:
        bytes_brutos = bytearray(rng.randrange(256) for _ in range(16))
        bytes_brutos[6] = (bytes_brutos[6] & 0x0F) | 0x40
        bytes_brutos[8] = (bytes_brutos[8] & 0x3F) | 0x80
        valor = str(uuid.UUID(bytes=bytes(bytes_brutos)))

    return Gerado(valor=valor, valido=True, corrupcao=None, seed=rng_seed)


def _corromper_delegando(valor: str, tipo: TipoDeChavePix, modo: Corrupcao, rng_seed: int) -> str:
    """Corrompe CPF, CNPJ e telefone reusando o módulo de cada formato."""
    if tipo is TipoDeChavePix.CPF:
        return mod_cpf.corromper(valor, modo, rng_seed).valor
    if tipo is TipoDeChavePix.CNPJ:
        return mod_cnpj.corromper(valor, modo, rng_seed).valor
    return mod_telefone.corromper(valor, modo, rng_seed).valor


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe uma chave PIX pelo modo pedido.

    Para CPF, CNPJ e telefone a corrupção **delega** ao módulo do formato: são
    eles que sabem o que é detectável ali, e duplicar a lógica aqui produziria
    duas réguas que divergem com o tempo.

    Args:
        valor: uma chave válida.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        A chave corrompida.

    Raises:
        ValueError: se a chave for inválida, ou se o modo não se aplicar ao tipo.
    """
    tipo = detectar_tipo(valor)
    if tipo is None:
        msg = f"nao da para corromper uma chave PIX invalida: {valor!r}"
        raise ValueError(msg)

    if tipo in (TipoDeChavePix.CPF, TipoDeChavePix.CNPJ, TipoDeChavePix.TELEFONE):
        return Gerado(
            valor=_corromper_delegando(valor, tipo, modo, rng_seed),
            valido=False,
            corrupcao=modo,
            seed=rng_seed,
        )

    if tipo is TipoDeChavePix.EMAIL:
        return Gerado(
            valor=_corromper_email(valor, modo),
            valido=False,
            corrupcao=modo,
            seed=rng_seed,
        )

    if modo is Corrupcao.MASCARA_ERRADA:
        corrompido = valor.replace("-", "")
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompido = valor[:-1]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        corrompido = "z" + valor[1:]
    elif modo is Corrupcao.FAIXA_INVALIDA:
        # Um UUID v1 legitimo: passa no formato, carrega timestamp e MAC, e NAO e
        # uma chave aleatoria. E a armadilha central deste modulo.
        corrompido = f"{valor[:14]}1{valor[15:]}"
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        corrompido = "00000000-0000-0000-0000-000000000000"
    else:
        msg = f"{modo.value} nao se aplica a chave aleatoria: nao ha digito verificador"
        raise ValueError(msg)

    return Gerado(valor=corrompido, valido=False, corrupcao=modo, seed=rng_seed)


def _corromper_email(valor: str, modo: Corrupcao) -> str:
    """Corrompe uma chave de e-mail.

    Raises:
        ValueError: se o modo não se aplicar a e-mail.
    """
    usuario, _, dominio = valor.partition("@")
    if modo is Corrupcao.MASCARA_ERRADA:
        return valor.upper()
    if modo is Corrupcao.TAMANHO_ERRADO:
        sobra = TAMANHO_MAXIMO_DE_EMAIL - len(valor) + 1
        return f"{usuario}{'a' * sobra}@{dominio}"
    if modo is Corrupcao.CARACTERE_INVALIDO:
        return f"{usuario} x@{dominio}"
    if modo is Corrupcao.SEQUENCIA_REPETIDA:
        return f"{usuario}@@{dominio}"
    msg = f"{modo.value} nao se aplica a chave de e-mail"
    raise ValueError(msg)
