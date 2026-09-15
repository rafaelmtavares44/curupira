"""CEP: 8 dígitos, no formato `NNNNN-NNN`.

**Não tem dígito verificador.** A validade real é existência na base dos
Correios, que não consultamos e não devemos consultar. Aqui validamos formato e
faixa regional — o bloco inicial indica o estado.

O detalhe que quebra implementação ingênua
------------------------------------------
As faixas **não são um simples mapa do primeiro dígito**. Roraima ocupa
`69300-000` a `69399-999`, que está **dentro** do bloco do Amazonas
(`69000-000` a `69899-999`). Um validador que percorra as faixas em ordem
alfabética de UF atribui aquele intervalo ao Amazonas e nunca a Roraima.

Por isso `FAIXAS` é uma tupla **ordenada por especificidade**, com os sub-blocos
antes dos blocos que os contêm, e a busca devolve a primeira faixa que casa. A
ordem daquela tupla é comportamento, não estilo — há teste para ela.

Nota de privacidade: CEP identifica um logradouro, não uma pessoa. Um CEP real
associado a um nome fictício não é dado pessoal de ninguém. O risco mora na
combinação, não no campo. Ver SECURITY.md.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

from curupira.core.enums import Corrupcao
from curupira.formatos.base import Gerado, rng_de

TAMANHO: Final = 8

_NU: Final = re.compile(r"^\d{8}$")
_MASCARADO: Final = re.compile(r"^\d{5}-\d{3}$")


class FaixaDeCep(NamedTuple):
    """Um intervalo contínuo de CEP atribuído a uma unidade federativa."""

    uf: str
    inicio: int
    fim: int


FAIXAS: Final = (
    # Sub-blocos primeiro. Roraima mora dentro do intervalo do Amazonas, e uma
    # busca que nao respeite esta ordem nunca devolve RR.
    FaixaDeCep("RR", 69300000, 69399999),
    FaixaDeCep("AP", 68900000, 68999999),
    FaixaDeCep("SP", 1000000, 19999999),
    FaixaDeCep("RJ", 20000000, 28999999),
    FaixaDeCep("ES", 29000000, 29999999),
    FaixaDeCep("MG", 30000000, 39999999),
    FaixaDeCep("BA", 40000000, 48999999),
    FaixaDeCep("SE", 49000000, 49999999),
    FaixaDeCep("PE", 50000000, 56999999),
    FaixaDeCep("AL", 57000000, 57999999),
    FaixaDeCep("PB", 58000000, 58999999),
    FaixaDeCep("RN", 59000000, 59999999),
    FaixaDeCep("CE", 60000000, 63999999),
    FaixaDeCep("PI", 64000000, 64999999),
    FaixaDeCep("MA", 65000000, 65999999),
    FaixaDeCep("PA", 66000000, 68899999),
    FaixaDeCep("AM", 69000000, 69899999),
    FaixaDeCep("AC", 69900000, 69999999),
    FaixaDeCep("DF", 70000000, 72799999),
    FaixaDeCep("GO", 72800000, 76799999),
    FaixaDeCep("RO", 76800000, 76999999),
    FaixaDeCep("TO", 77000000, 77999999),
    FaixaDeCep("MT", 78000000, 78899999),
    FaixaDeCep("MS", 79000000, 79999999),
    FaixaDeCep("PR", 80000000, 87999999),
    FaixaDeCep("SC", 88000000, 89999999),
    FaixaDeCep("RS", 90000000, 99999999),
)
"""As 27 faixas, ordenadas por especificidade. Fonte: Correios, set/2026."""

BURACOS: Final = ((0, 999999), (78900000, 78999999))
"""Intervalos que não pertencem a nenhuma UF, usados por `FAIXA_INVALIDA`.

O primeiro é o bloco abaixo de São Paulo; o segundo fica entre o fim do Mato
Grosso e o começo do Mato Grosso do Sul. Um CEP aqui tem oito dígitos, passa em
qualquer verificação de formato, e mesmo assim não existe — que é exatamente o
tipo de erro que um agente entrega com cara de sucesso.
"""


def _digitos(valor: str) -> str | None:
    """Extrai os 8 dígitos, se a grafia for uma das duas aceitas."""
    if not (_NU.match(valor) or _MASCARADO.match(valor)):
        return None
    return valor.replace("-", "")


def uf_de(valor: str) -> str | None:
    """Descobre a unidade federativa de um CEP.

    Args:
        valor: o CEP, com ou sem hífen.

    Returns:
        A sigla da UF, ou `None` se a grafia for inválida ou o número cair num
        intervalo não atribuído.
    """
    digitos = _digitos(valor)
    if digitos is None:
        return None
    numero = int(digitos)
    return next((f.uf for f in FAIXAS if f.inicio <= numero <= f.fim), None)


def validar(valor: str) -> bool:
    """Valida formato e faixa regional de um CEP.

    Duas grafias são aceitas, e só elas: oito dígitos nus, ou `00000-000`. A
    rigidez é proposital — sem ela, `Corrupcao.MASCARA_ERRADA` não seria
    detectável.

    Args:
        valor: o CEP, com ou sem hífen.

    Returns:
        `True` se tem 8 dígitos numa das duas grafias e cai numa faixa atribuída.
    """
    return uf_de(valor) is not None


def mascarar(nu: str) -> str:
    """Formata oito dígitos nus como `00000-000`.

    Args:
        nu: os oito dígitos.

    Returns:
        O CEP mascarado.
    """
    return f"{nu[:5]}-{nu[5:]}"


def intervalos_de(uf: str) -> tuple[tuple[int, int], ...]:
    """Os intervalos que pertencem **de fato** a uma unidade federativa.

    ACHADO, encontrado pelo Hypothesis e não por leitura
    -----------------------------------------------------
    Sortear um número dentro de `FaixaDeCep("AM", 69000000, 69899999)` cai, em
    cerca de 11% das vezes, no bloco de Roraima — que mora dentro daquele
    intervalo. O CEP resultante é perfeitamente válido e pertence a **outro
    estado**, o que arruinaria toda tarefa em que a UF é o gabarito.

    Este é o tipo de defeito que leitura não pega: a faixa está certa, o sorteio
    está certo, e a composição dos dois está errada. Por isso a subtração dos
    sub-blocos é explícita, e o teste de propriedade cobra o resultado.

    Args:
        uf: a sigla da unidade federativa.

    Returns:
        Os intervalos fechados da UF, já sem os blocos aninhados de outras.

    Raises:
        ValueError: se a UF não existir.
    """
    procurada = next((f for f in FAIXAS if f.uf == uf.upper()), None)
    if procurada is None:
        msg = f"unidade federativa desconhecida: {uf!r}"
        raise ValueError(msg)

    aninhados = sorted(
        (f.inicio, f.fim)
        for f in FAIXAS
        if f.uf != procurada.uf and procurada.inicio <= f.inicio and f.fim <= procurada.fim
    )
    intervalos: list[tuple[int, int]] = []
    cursor = procurada.inicio
    for inicio, fim in aninhados:
        if cursor < inicio:
            intervalos.append((cursor, inicio - 1))
        cursor = max(cursor, fim + 1)
    if cursor <= procurada.fim:
        intervalos.append((cursor, procurada.fim))
    return tuple(intervalos)


def gerar(rng_seed: int, *, uf: str | None = None, com_mascara: bool = True) -> Gerado:
    """Gera um CEP de formato válido.

    Com `uf`, o sorteio respeita os sub-blocos aninhados: um CEP pedido para o
    Amazonas nunca cai em Roraima. Ver `intervalos_de`.

    Args:
        rng_seed: a seed.
        uf: se informada, restringe à faixa da unidade federativa.
        com_mascara: se verdadeiro, devolve `00000-000`.

    Returns:
        O CEP gerado.

    Raises:
        ValueError: se a UF não existir.
    """
    rng = rng_de(rng_seed)
    escolhida = uf.upper() if uf is not None else rng.choice(FAIXAS).uf
    intervalos = intervalos_de(escolhida)
    # Sorteio ponderado pelo tamanho: sem isso, o pedaco de 300 mil CEPs do
    # Amazonas antes de Roraima teria a mesma chance do pedaco de 500 mil depois.
    inicio, fim = rng.choices(intervalos, weights=[f - i + 1 for i, f in intervalos])[0]

    nu = f"{rng.randint(inicio, fim):08d}"
    return Gerado(
        valor=mascarar(nu) if com_mascara else nu,
        valido=True,
        corrupcao=None,
        seed=rng_seed,
    )


def corromper(valor: str, modo: Corrupcao, rng_seed: int) -> Gerado:
    """Corrompe um CEP pelo modo pedido.

    Args:
        valor: um CEP de formato válido.
        modo: o modo de corrupção.
        rng_seed: a seed.

    Returns:
        O CEP corrompido.

    Raises:
        ValueError: se o valor não for um CEP válido, ou se o modo não se aplicar
            — CEP não tem dígito verificador, então `DV_TROCADO` e `TRANSPOSICAO`
            não têm como ser garantidamente detectáveis aqui. Recusar é melhor do
            que devolver um "corrompido" que o validador aprova, porque isso seria
            um gabarito errado disfarçado de tarefa.
    """
    digitos = _digitos(valor)
    if digitos is None:
        msg = f"nao da para corromper um CEP invalido: {valor!r}"
        raise ValueError(msg)

    rng = rng_de(rng_seed)
    mascarado = "-" in valor

    if modo is Corrupcao.FAIXA_INVALIDA:
        inicio, fim = rng.choice(BURACOS)
        nu = f"{rng.randint(inicio, fim):08d}"
        corrompido = mascarar(nu) if mascarado else nu
    elif modo is Corrupcao.MASCARA_ERRADA:
        corrompido = f"{digitos[:2]}.{digitos[2:5]}-{digitos[5:]}"
    elif modo is Corrupcao.TAMANHO_ERRADO:
        corrompido = digitos[:-1]
    elif modo is Corrupcao.CARACTERE_INVALIDO:
        posicao = rng.randrange(TAMANHO)
        nu = digitos[:posicao] + "X" + digitos[posicao + 1 :]
        corrompido = mascarar(nu) if mascarado else nu
    elif modo is Corrupcao.SEQUENCIA_REPETIDA:
        # `00000000` e o unico repetido que cai num buraco. Os demais (11111111,
        # 22222222...) sao CEPs de faixa atribuida, e o validador os aprova — o
        # que faz de CEP um contraexemplo util a intuicao herdada do CPF.
        corrompido = mascarar("0" * TAMANHO) if mascarado else "0" * TAMANHO
    else:
        msg = (
            f"{modo.value} nao se aplica a CEP: nao ha digito verificador, entao "
            "nao ha como garantir que o resultado seja reprovado"
        )
        raise ValueError(msg)

    return Gerado(valor=corrompido, valido=False, corrupcao=modo, seed=rng_seed)
