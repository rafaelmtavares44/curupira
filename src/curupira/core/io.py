r"""Escrita de arquivo com fim de linha fixo em LF, em qualquer sistema.

Por que este módulo existe
--------------------------
`Path.write_text` e `Path.open("w")` abrem em **modo texto**. Nesse modo o
CPython traduz todo `\n` para `os.linesep` na saída — que é `\r\n` no Windows.
O mesmo programa, com a mesma entrada, produz bytes diferentes conforme o
sistema operacional de quem rodou.

Para a maioria dos programas isso é um detalhe. Para o Curupira é um defeito de
reprodutibilidade, porque o registro de uma rodada grava o SHA-256 **dos bytes**
do arquivo da suíte (`suite_sha256`, em `cli.py`). Com a tradução ligada, a
mesma suíte hasheia de um jeito no Windows e de outro no Linux, e uma conferência
futura acusaria adulteração onde houve apenas um `git checkout`.

O `.gitattributes` do projeto já força `eol=lf` no repositório. Isso resolve o
que o git toca, e só. Um arquivo **gerado** pelo Curupira nasce com o fim de
linha do sistema antes de o git ver qualquer coisa — e, se ele nunca for
versionado (um `raw.jsonl` de rodada, por exemplo), o git nunca vai ver.

A solução
---------
Escrever em **modo binário**, sempre. O modo binário não traduz nada, em
plataforma nenhuma. Não é "lembrar de passar `newline='\n'`": é remover a
possibilidade de esquecer.

`tests/test_io.py` guarda a regra com um teste que varre o próprio código-fonte
e recusa qualquer escrita de arquivo feita fora daqui. Sem esse teste, a
correção dura até a próxima vez que alguém escrever um `write_text` distraído.

Leitura não precisa deste cuidado: o modo texto na leitura faz *universal
newlines*, que converte `\r\n` para `\n` de volta. Arquivos antigos, gravados
antes desta correção, continuam sendo lidos certo.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Final

CODIFICACAO: Final = "utf-8"
"""A única codificação que o projeto grava. Declarada, não herdada do sistema."""


def gravar_texto(caminho: Path, conteudo: str) -> None:
    """Grava texto em UTF-8, com LF, criando os diretórios que faltarem.

    Substitui `Path.write_text` em todo o pacote. Os bytes gravados são
    exatamente `conteudo.encode("utf-8")` — nenhuma tradução de fim de linha,
    em nenhum sistema operacional.

    Args:
        caminho: o arquivo de destino. Os diretórios pais são criados.
        conteudo: o texto a gravar.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo.encode(CODIFICACAO))


@contextmanager
def acrescentar_linhas(caminho: Path) -> Iterator[EscritorDeLinhas]:
    """Abre um arquivo para acrescentar linhas, em UTF-8 e com LF.

    Substitui `Path.open("a")` em todo o pacote. Pensado para arquivos de linhas
    independentes, como o `raw.jsonl` de uma rodada.

    Args:
        caminho: o arquivo de destino. Os diretórios pais são criados.

    Yields:
        O escritor, com `escrever_linha` e `descarregar`.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("ab") as descritor:
        yield EscritorDeLinhas(descritor)


class EscritorDeLinhas:
    """Escreve linhas terminadas em LF num descritor binário.

    Não é um substituto geral de arquivo: expõe só o que o projeto usa, de
    propósito. A API estreita é o que impede alguém de voltar a escrever texto
    cru e reintroduzir a tradução de fim de linha.
    """

    def __init__(self, descritor: IO[bytes]) -> None:
        """Guarda o descritor já aberto em modo binário.

        Args:
            descritor: arquivo aberto em modo binário pelo `acrescentar_linhas`.
        """
        self._descritor = descritor

    def escrever_linha(self, texto: str) -> None:
        r"""Escreve `texto` seguido de um LF.

        Args:
            texto: a linha, sem o terminador. Um `\n` no fim seria duplicado.
        """
        self._descritor.write((texto + "\n").encode(CODIFICACAO))

    def descarregar(self) -> None:
        """Força a descarga do buffer para o sistema de arquivos.

        Uma rodada longa que morre no meio tem que deixar no disco tudo o que já
        custou dinheiro. O bruto é o ativo: perder resposta já paga por causa de
        buffer é o pior desperdício possível.
        """
        self._descritor.flush()
