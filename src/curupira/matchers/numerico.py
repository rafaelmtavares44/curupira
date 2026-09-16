"""Matchers numéricos, incluindo os que existem por causa do PT-BR.

`moeda_normalizada` é o matcher mais importante do projeto: `1.234,56` em
português é mil duzentos e trinta e quatro reais e cinquenta e seis centavos, e
lido à moda anglófona seria mil duzentos e trinta e quatro *mil*. O erro é
silencioso e de três ordens de grandeza.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Final

from pydantic import JsonValue

CASAS_DE_CENTAVOS: Final = 2
_MOEDA: Final = re.compile(r"^(?:R\$)?([-+]?[\d.,]+)$", re.IGNORECASE)
"""Casa o texto INTEIRO. Extrair um numero do meio de lixo seria adivinhar."""

CHAVE_DOS_FORMATOS: Final = "formatos_aceitos"
"""O parametro obrigatorio de `data_iso`. Ver `data_iso` para o motivo."""


def _e_inteiro(valor: JsonValue) -> bool:
    """`True` só para int de verdade.

    `isinstance(True, int)` é verdadeiro em Python, e um `True` chegando onde se
    espera `valor_centavos` não é "1 centavo", é um agente confuso.
    """
    return isinstance(valor, int) and not isinstance(valor, bool)


def exact_int(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Igualdade exata de inteiro, sem coerção de string.

    Sem coerção de propósito: se a ferramenta declara `valor_centavos: integer` e
    o agente manda `"123456"`, ele errou o contrato — e essa é a informação.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência.
        params: ignorado.

    Returns:
        `True` se ambos são inteiros e iguais.
    """
    del params
    return _e_inteiro(observado) and _e_inteiro(esperado) and observado == esperado


def _como_float(valor: JsonValue) -> float | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int | float):
        return float(valor)
    return None


def tolerancia_numerica(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    """Igualdade numérica com tolerância absoluta ou relativa.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência.
        params: `abs_tol` e/ou `rel_tol`.

    Returns:
        `True` se a diferença cabe em alguma das tolerâncias.
    """
    a = _como_float(observado)
    b = _como_float(esperado)
    if a is None or b is None:
        return False
    abs_tol = _como_float(params.get("abs_tol", 0.0)) or 0.0
    rel_tol = _como_float(params.get("rel_tol", 0.0)) or 0.0
    diferenca = abs(a - b)
    return diferenca <= abs_tol or diferenca <= rel_tol * abs(b)


def para_centavos(texto: str) -> int | None:
    """Converte a grafia de um valor monetário em centavos.

    Política, declarada porque a ambiguidade é o objeto do benchmark:

    - Com ponto **e** vírgula, o separador que aparece por último é o decimal.
      Resolve `1.234,56` (PT-BR) e `1,234.56` (EN) sem adivinhar idioma.
    - Com um separador só, ele é decimal **apenas** se vier seguido de exatamente
      duas casas; caso contrário é separador de milhar. Assim `1234,56` vira
      123456 e `1.234` vira 123400.
    - `1,234` é genuinamente ambíguo — mil duzentos e trinta e quatro em inglês,
      um e vinte e três em português. A regra acima o lê como milhar. Uma tarefa
      que dependa desse caso deve declarar o esperado e não usar este matcher.

    Args:
        texto: o valor escrito.

    Returns:
        O valor em centavos, ou `None` se não for interpretável.
    """
    casou = _MOEDA.fullmatch(texto.replace(" ", "").replace("\u00a0", ""))
    if casou is None:
        return None
    bruto = casou.group(1)
    negativo = bruto.startswith("-")
    bruto = bruto.lstrip("+-")
    if not bruto or not any(c.isdigit() for c in bruto):
        return None

    ultimo_ponto = bruto.rfind(".")
    ultima_virgula = bruto.rfind(",")
    corte = max(ultimo_ponto, ultima_virgula)

    if corte == -1:
        inteiro, decimais = bruto, ""
    else:
        cauda = bruto[corte + 1 :]
        so_um_tipo = ultimo_ponto == -1 or ultima_virgula == -1
        decimal = len(cauda) == CASAS_DE_CENTAVOS if so_um_tipo else True
        inteiro, decimais = (bruto[:corte], cauda) if decimal else (bruto, "")

    digitos_inteiros = re.sub(r"[.,]", "", inteiro)
    if not digitos_inteiros.isdigit() or (decimais and not decimais.isdigit()):
        return None
    centavos = int(digitos_inteiros) * 100 + int((decimais or "0").ljust(2, "0")[:2])
    return -centavos if negativo else centavos


def moeda_normalizada(
    observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]
) -> bool:
    """Compara valores monetários em centavos, aceitando as grafias usuais.

    Args:
        observado: o valor que o agente enviou.
        esperado: o valor de referência, em centavos.
        params: `aceitar_string` (padrão `True`) para permitir `"1.234,56"` além
            do inteiro.

    Returns:
        `True` se, normalizado a centavos, o valor confere.
    """
    if not _e_inteiro(esperado):
        return False
    if _e_inteiro(observado):
        return observado == esperado
    if not isinstance(observado, str) or params.get("aceitar_string") is False:
        return False
    return para_centavos(observado) == esperado


def para_data(texto: str, formatos: tuple[str, ...]) -> date | None:
    """Converte a grafia de uma data em `date`, tentando os formatos em ordem.

    Args:
        texto: a data escrita.
        formatos: os formatos `strptime` aceitos, em ordem de prioridade.

    Returns:
        A data, ou `None` se nenhum formato casar.
    """
    limpo = texto.strip()
    for formato in formatos:
        try:
            return datetime.strptime(limpo, formato).date()
        except ValueError:
            continue
    return None


def data_iso(observado: JsonValue, esperado: JsonValue, params: Mapping[str, JsonValue]) -> bool:
    """Compara datas normalizadas para o calendário, não para o texto.

    `03/04/2026` é 3 de abril em português e 4 de março em inglês. A ambiguidade
    é o teste; a lista de formatos aceitos é a régua, e ela **vem da tarefa** —
    o matcher não adivinha idioma.

    Por que `formatos_aceitos` é obrigatório
    ----------------------------------------
    Até a Entrega 16 havia um default, `("%d/%m/%Y", "%Y-%m-%d", ...)`, com a
    justificativa de que *"o dataset nasce em PT-BR"*. Era um viés de locale
    escondido num valor omitido, e ele contaminava o Delta:

    - na versão PT-BR, um agente que **devolvesse a entrada sem converter**
      (`"05/03/2026"`) era lido como 5 de março e **acertava**;
    - na versão EN-US, o mesmo não-trabalho (`"03/05/2026"`) era lido como 3 de
      maio e **errava**.

    Mesmo `arg_specs` nos dois lados, mesmo YAML — e mesmo assim a régua
    favorecia o português em alguns pontos. O Delta estaria medindo, em parte, o
    nosso próprio default. É a mesma armadilha que a ADR 0007 D4 eliminou na
    resposta da ferramenta, aqui num lugar mais difícil de enxergar.

    Omitir o parâmetro agora é erro de configuração, não um default silencioso.
    O lint `regua-de-data-explicita` pega isso antes de qualquer rodada; o
    `ValueError` é a rede embaixo, para o caso de alguém pular o lint.

    Args:
        observado: o valor que o agente enviou.
        esperado: a data de referência, normalmente em ISO.
        params: `formatos_aceitos`, lista **não vazia** de formatos `strptime`.

    Returns:
        `True` se as datas normalizadas coincidem.

    Raises:
        ValueError: se `formatos_aceitos` faltar ou não trouxer nenhum formato.
    """
    bruto = params.get(CHAVE_DOS_FORMATOS)
    formatos = tuple(f for f in bruto if isinstance(f, str)) if isinstance(bruto, list) else ()
    if not formatos:
        raise ValueError(
            f"o matcher 'data_iso' exige '{CHAVE_DOS_FORMATOS}' com ao menos um "
            "formato strptime. Nao ha default: um default de data e um vies de "
            "locale escondido, e ele entraria direto no Delta PT-BR"
        )

    if not isinstance(observado, str) or not isinstance(esperado, str):
        return False
    a = para_data(observado, formatos)
    b = para_data(esperado, (*formatos, "%Y-%m-%d"))
    return a is not None and a == b
