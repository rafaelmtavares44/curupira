r"""A escrita de arquivo produz LF em qualquer sistema — e ninguém escapa disso.

Dois tipos de teste aqui, e os dois precisam existir:

- Os de comportamento, que exercitam `gravar_texto` e `acrescentar_linhas`.
- `test_nenhuma_escrita_de_arquivo_fora_do_modulo_de_io`, que lê o próprio
  código-fonte com `ast` e recusa qualquer escrita feita fora do
  `curupira.core.io`.

O segundo é o que faz a correção durar. Os cinco pontos de escrita que existiam
antes dele foram corrigidos à mão; o sexto, escrito daqui a dois meses por
alguém copiando um `write_text` de um tutorial, seria corrigido por ninguém.

Honestidade sobre o alcance
---------------------------
Os testes de comportamento **não distinguem** o código certo do errado quando
rodam em Linux: lá o modo texto do CPython não traduz `\n` para nada, então
`write_text` e `write_bytes` produzem os mesmos bytes. Eles distinguem no
Windows, que é onde este projeto é desenvolvido, e é lá que o defeito apareceu.

O teste estrutural, esse sim, falha em qualquer sistema operacional enquanto
houver uma escrita fora do lugar. É ele que carrega a garantia no CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from curupira.core.io import acrescentar_linhas, gravar_texto

RAIZ_DO_PACOTE = Path(__file__).resolve().parent.parent / "src" / "curupira"
MODULO_DE_IO = RAIZ_DO_PACOTE / "core" / "io.py"

METODOS_DE_ESCRITA = frozenset({"write_text", "write_bytes"})
"""Sempre escrita, qualquer que seja o argumento. Proibidos fora do `core.io`."""

MODOS_DE_ESCRITA = frozenset("wax+")
"""Se a string de modo contém uma destas letras, o arquivo abre para escrita."""


# --------------------------------------------------------------------------
# Comportamento
# --------------------------------------------------------------------------


def test_gravar_texto_produz_exatamente_os_bytes_do_conteudo(tmp_path: Path) -> None:
    conteudo = "primeira\nsegunda\nterceira\n"
    destino = tmp_path / "arquivo.txt"

    gravar_texto(destino, conteudo)

    assert destino.read_bytes() == conteudo.encode("utf-8")
    assert b"\r" not in destino.read_bytes()


def test_gravar_texto_preserva_acentos_em_utf8(tmp_path: Path) -> None:
    """O dataset é em português: um `latin-1` herdado do sistema corromperia tudo."""
    destino = tmp_path / "acentos.txt"

    gravar_texto(destino, "transferência para o favorecido Gonçalves\n")

    assert destino.read_text(encoding="utf-8") == "transferência para o favorecido Gonçalves\n"


def test_gravar_texto_cria_os_diretorios_que_faltam(tmp_path: Path) -> None:
    destino = tmp_path / "um" / "dois" / "tres.txt"

    gravar_texto(destino, "conteudo")

    assert destino.read_text(encoding="utf-8") == "conteudo"


def test_gravar_texto_sobrescreve_o_arquivo_inteiro(tmp_path: Path) -> None:
    """Sem isto, um relatório novo e curto deixaria a cauda do relatório antigo."""
    destino = tmp_path / "arquivo.txt"
    gravar_texto(destino, "conteudo bem mais longo do que o proximo")

    gravar_texto(destino, "curto")

    assert destino.read_text(encoding="utf-8") == "curto"


def test_acrescentar_linhas_termina_cada_linha_em_lf(tmp_path: Path) -> None:
    destino = tmp_path / "bruto.jsonl"

    with acrescentar_linhas(destino) as escritor:
        escritor.escrever_linha('{"id": "t2-money-0001"}')
        escritor.escrever_linha('{"id": "t2-money-0002"}')

    assert destino.read_bytes() == (b'{"id": "t2-money-0001"}\n{"id": "t2-money-0002"}\n')


def test_acrescentar_linhas_acrescenta_em_vez_de_sobrescrever(tmp_path: Path) -> None:
    """Uma rodada retomada não pode apagar o bruto que já custou dinheiro."""
    destino = tmp_path / "bruto.jsonl"
    with acrescentar_linhas(destino) as escritor:
        escritor.escrever_linha("primeira")

    with acrescentar_linhas(destino) as escritor:
        escritor.escrever_linha("segunda")

    assert destino.read_text(encoding="utf-8") == "primeira\nsegunda\n"


def test_acrescentar_linhas_cria_os_diretorios_que_faltam(tmp_path: Path) -> None:
    destino = tmp_path / "rodada" / "bruto.jsonl"

    with acrescentar_linhas(destino) as escritor:
        escritor.escrever_linha("linha")

    assert destino.read_text(encoding="utf-8") == "linha\n"


def test_descarregar_poe_a_linha_no_disco_antes_de_fechar(tmp_path: Path) -> None:
    """O ponto de `descarregar`: o arquivo já vale algo com o descritor aberto."""
    destino = tmp_path / "bruto.jsonl"

    with acrescentar_linhas(destino) as escritor:
        escritor.escrever_linha("paga e registrada")
        escritor.descarregar()
        assert destino.read_text(encoding="utf-8") == "paga e registrada\n"


# --------------------------------------------------------------------------
# A garantia estrutural
# --------------------------------------------------------------------------


def _e_modo_de_escrita(no: ast.expr | None) -> bool:
    """Diz se o argumento de modo de um `open` abre o arquivo para escrita.

    Um modo que não é literal (uma variável, por exemplo) conta como escrita:
    na dúvida o teste reprova e alguém explica, em vez de o teste calar.

    Args:
        no: o nó do argumento de modo, ou `None` quando não há modo — e aí é
            leitura, que é o padrão do `open`.

    Returns:
        `True` se o arquivo abre para escrita.
    """
    if no is None:
        return False
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return bool(MODOS_DE_ESCRITA & set(no.value))
    return True


def _modo_do_open(chamada: ast.Call) -> ast.expr | None:
    """Extrai o argumento de modo de uma chamada a `open`, posicional ou nomeado.

    As duas formas põem o modo em posições diferentes: `Path.open(modo)` o traz
    como primeiro argumento, enquanto o `open(caminho, modo)` embutido o traz
    como segundo.

    Args:
        chamada: o nó da chamada.

    Returns:
        O nó do argumento de modo, ou `None` quando a chamada não passa modo.
    """
    for palavra in chamada.keywords:
        if palavra.arg == "mode":
            return palavra.value
    posicao = 0 if isinstance(chamada.func, ast.Attribute) else 1
    if len(chamada.args) > posicao:
        return chamada.args[posicao]
    return None


def _escritas_no_arquivo(caminho: Path) -> list[str]:
    """Encontra toda escrita de arquivo num módulo.

    Args:
        caminho: o arquivo `.py` a inspecionar.

    Returns:
        Uma descrição por ocorrência, com o número da linha.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achados: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        if isinstance(alvo, ast.Attribute) and alvo.attr in METODOS_DE_ESCRITA:
            achados.append(f"linha {no.lineno}: .{alvo.attr}(")
        elif (
            isinstance(alvo, ast.Attribute)
            and alvo.attr == "open"
            and _e_modo_de_escrita(_modo_do_open(no))
        ):
            achados.append(f"linha {no.lineno}: .open( em modo de escrita")
        elif (
            isinstance(alvo, ast.Name)
            and alvo.id == "open"
            and _e_modo_de_escrita(_modo_do_open(no))
        ):
            achados.append(f"linha {no.lineno}: open( em modo de escrita")
    return achados


def test_nenhuma_escrita_de_arquivo_fora_do_modulo_de_io() -> None:
    """Toda escrita do pacote passa pelo `core.io`, que grava em modo binário.

    Este é o teste que a Entrega 10 existe para criar. Ele falha enquanto
    houver um `write_text`, um `write_bytes` ou um `open` em modo de escrita em
    qualquer módulo do pacote fora do `core/io.py`.

    Se um dia um módulo precisar mesmo escrever direto — um formato binário
    grande, um `mmap` —, a saída **não** é apagar este teste: é acrescentar a
    função ao `core.io` e chamá-la de lá. O ponto do teste é que a exceção seja
    discutida, não silenciosa.
    """
    problemas: dict[str, list[str]] = {}
    for modulo in sorted(RAIZ_DO_PACOTE.rglob("*.py")):
        if modulo == MODULO_DE_IO:
            continue
        achados = _escritas_no_arquivo(modulo)
        if achados:
            problemas[str(modulo.relative_to(RAIZ_DO_PACOTE))] = achados

    assert not problemas, (
        "escrita de arquivo fora de curupira.core.io — use gravar_texto ou "
        f"acrescentar_linhas: {problemas}"
    )


def test_o_modulo_de_io_realmente_escreve_em_modo_binario() -> None:
    """A exceção do teste acima não pode ser uma isenção em branco.

    Se alguém trocar o `write_bytes` do `core/io.py` por um `write_text`, o
    teste estrutural continuaria verde — o módulo está na lista de exceção — e
    a tradução de fim de linha voltaria em silêncio, exatamente onde ela foi
    proibida. Este teste fecha essa porta.
    """
    achados = _escritas_no_arquivo(MODULO_DE_IO)
    assert achados, "o modulo de io deveria conter as escritas do pacote"
    assert all("write_text" not in achado for achado in achados), (
        f"o modulo de io voltou a escrever em modo texto: {achados}"
    )


@pytest.mark.parametrize(
    ("codigo", "espera_achado"),
    [
        ('p.open("r")', False),
        ("p.open()", False),
        ('p.open(encoding="utf-8")', False),
        ('p.open("w")', True),
        ('p.open("ab")', True),
        ('p.open(mode="a", encoding="utf-8")', True),
        ("p.open(modo)", True),
        ("p.write_text(x)", True),
        ("p.write_bytes(x)", True),
        ('open("x.txt")', False),
        ('open("x.txt", "w")', True),
    ],
)
def test_o_detector_reconhece_escrita_e_ignora_leitura(
    tmp_path: Path, codigo: str, espera_achado: bool
) -> None:
    """O detector é o que sustenta a garantia: ele mesmo precisa de teste.

    Um detector que não enxerga escrita transforma o teste estrutural em
    decoração verde.
    """
    modulo = tmp_path / "amostra.py"
    modulo.write_text(codigo, encoding="utf-8")

    assert bool(_escritas_no_arquivo(modulo)) is espera_achado
