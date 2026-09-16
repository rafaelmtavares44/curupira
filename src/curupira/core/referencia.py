"""Confere que uma referência de teste aponta para um teste que existe.

Por que isto existe
-------------------
A errata exige `test_ref`: o caminho do teste que reproduz o defeito. Sem teste,
a entrada não entra — é a trava que separa *"esta tarefa tem gabarito errado"* de
*"o modelo X vai mal nessa tarefa"*.

Só que, até aqui, `test_ref` era **texto livre que ninguém conferia**. Um campo
com esse nome e sem verificação é promessa, não garantia — exatamente o mesmo
defeito de forma que a opção `--framework` tinha até a Entrega 12, quando era um
rótulo que não mudava nada.

O que é conferido, e o que não é
---------------------------------
Aqui se confere que o arquivo existe e que uma função com aquele nome está
definida nele, por análise sintática. **Não** se confere que o teste falha na
tarefa defeituosa, nem que ele passa depois da correção — isso exigiria executar
o pytest, e o `curupira` é o pacote de runtime, não o de desenvolvimento.

A verificação é o piso, não o teto. Ela pega o caso real e frequente: o caminho
com typo, o teste renomeado, o arquivo que nunca foi criado.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SEPARADOR: Final = "::"
"""Convenção do pytest: `caminho/do/arquivo.py::nome_do_teste`."""

PARTES_ESPERADAS: Final = 2
"""Caminho e nome. Três partes seriam classe de teste, que não aceitamos."""


def partes(referencia: str) -> tuple[str, str] | None:
    """Separa uma referência em caminho e nome do teste.

    Args:
        referencia: a referência no formato do pytest.

    Returns:
        O par `(caminho, nome)`, ou `None` quando a referência não tem a forma
        esperada. Classe aninhada (`arquivo.py::Classe::metodo`) devolve `None`:
        o projeto não usa classes de teste, e aceitar uma forma que não sabemos
        verificar seria fingir verificação.
    """
    pedacos = referencia.split(SEPARADOR)
    if len(pedacos) != PARTES_ESPERADAS:
        return None
    caminho, nome = (p.strip() for p in pedacos)
    if not caminho.endswith(".py") or not nome.isidentifier():
        return None
    return caminho, nome


def problema(raiz: Path, referencia: str) -> str | None:
    """Diz o que há de errado com uma referência de teste.

    Args:
        raiz: a raiz do repositório, contra a qual o caminho é resolvido.
        referencia: a referência no formato do pytest.

    Returns:
        A explicação do problema, ou `None` quando a referência é válida.
    """
    separadas = partes(referencia)
    if separadas is None:
        return (
            f"'{referencia}' nao tem a forma 'tests/arquivo.py::nome_do_teste'. "
            "Classe de teste nao e aceita: o projeto nao usa, e aceitar uma forma "
            "que nao sabemos conferir seria fingir verificacao"
        )

    caminho, nome = separadas
    arquivo = raiz / caminho
    if not arquivo.is_file():
        return f"o arquivo '{caminho}' nao existe"

    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as falha:
        return f"'{caminho}' nao pode ser lido como Python: {falha}"

    definidas = {
        no.name for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    if nome not in definidas:
        return f"'{caminho}' existe, mas nao define '{nome}'"
    return None
