"""A exclusão dos SHA-256 no `detect-secrets` não cegou o detector.

Por que este arquivo existe
---------------------------
Toda suíte congelada guarda o SHA-256 de cada tarefa, uma linha por tarefa. O
`detect-secrets` classifica isso como `Hex High Entropy String` e reprova o
commit — corretamente, pelo critério dele, e inutilmente, pelo nosso. Numa suíte
de sessenta tarefas seriam sessenta falsos positivos, e o desfecho previsível é
alguém desligar o hook inteiro.

A saída foi `--exclude-secrets ^[0-9a-f]{64}$`: ignorar um achado quando o
**valor** é exatamente 64 hexadecimais minúsculos. Isso é uma exceção num portão
de segurança, e exceção em portão de segurança só se justifica com prova de que
o portão continua fechado para o que importa.

Os testes abaixo são essa prova. Eles rodam o hook de verdade, com os argumentos
lidos do `.pre-commit-config.yaml`, e conferem os dois lados:

- um SHA-256 passa;
- uma chave de provedor, e todo hexadecimal que **não** é um SHA-256, continua
  sendo pega.

Ler os argumentos do arquivo de configuração, em vez de repeti-los aqui, é o que
impede teste e portão de divergirem: afrouxar a exclusão no YAML faz estes
testes falharem.

Nenhuma chave real aparece aqui. As amostras são montadas por concatenação em
tempo de execução, de propósito: escritas como literal, o próprio
`detect-secrets` acusaria este arquivo.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / ".pre-commit-config.yaml"

SHA256_DE_EXEMPLO = "4136fdcb42d97daff5103a3fbbf6bee6ec719fdd2c69bd2367d6a5f3acce5ea0"
"""Um SHA-256 qualquer, com a forma exata que a exclusão libera."""


def _argumentos_do_hook() -> list[str]:
    """Lê a linha de comando do hook `detect-secrets` do `.pre-commit-config.yaml`.

    Returns:
        Os argumentos, com `python` trocado pelo interpretador que roda os
        testes — senão o subprocesso cairia no Python do sistema, sem as
        dependências de desenvolvimento.
    """
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"]]
    entrada = next(hook["entry"] for hook in hooks if hook["id"] == "detect-secrets")
    argumentos = shlex.split(entrada)
    assert argumentos[0] == "python", f"o hook nao comeca com python: {argumentos[0]}"
    return [sys.executable, *argumentos[1:]]


def _acusa_arquivo(alvo: Path) -> bool:
    """Roda o hook sobre um arquivo já existente e diz se ele reprovou.

    Args:
        alvo: o arquivo a examinar.

    Returns:
        `True` se o hook reprovou (achou segredo).
    """
    processo = subprocess.run(  # noqa: S603 - comando lido do proprio repositorio
        [*_argumentos_do_hook(), str(alvo)],
        cwd=RAIZ,
        capture_output=True,
        check=False,
    )
    return processo.returncode != 0


def _acusa(conteudo: str, tmp_path: Path) -> bool:
    """Roda o hook sobre um arquivo temporário com `conteudo`.

    Args:
        conteudo: o texto do arquivo a examinar.
        tmp_path: o diretório temporário do pytest.

    Returns:
        `True` se o hook reprovou (achou segredo).
    """
    alvo = tmp_path / "amostra.txt"
    alvo.write_text(conteudo + "\n", encoding="utf-8")
    return _acusa_arquivo(alvo)


# --------------------------------------------------------------------------
# A exclusão existe
# --------------------------------------------------------------------------


def test_o_hook_declara_a_exclusao_de_sha256() -> None:
    """Sem a flag, toda suíte congelada reprova o commit."""
    argumentos = _argumentos_do_hook()
    assert "--exclude-secrets" in argumentos, (
        "o hook perdeu a exclusao dos SHA-256: toda suite congelada vai reprovar"
    )
    padrao = argumentos[argumentos.index("--exclude-secrets") + 1]
    assert padrao == "^[0-9a-f]{64}$", (
        f"o padrao da exclusao mudou para {padrao!r}. Se foi de proposito, ajuste "
        "estes testes junto e explique por que o novo padrao continua estreito."
    )


def test_um_sha256_passa(tmp_path: Path) -> None:
    """O caso que motivou tudo: o hash de uma tarefa na suíte congelada."""
    assert not _acusa(f"  sha256: {SHA256_DE_EXEMPLO}", tmp_path)


# --------------------------------------------------------------------------
# E não cegou nada
# --------------------------------------------------------------------------


def test_chave_de_provedor_continua_sendo_pega(tmp_path: Path) -> None:
    """A prova de que a exceção não abriu o portão.

    A amostra é montada em tempo de execução: escrita como literal, este
    arquivo seria acusado pelo próprio `detect-secrets`.
    """
    chave = "AKIA" + "Z" * 16
    assert _acusa(f"aws_access_key_id = {chave}", tmp_path)


@pytest.mark.parametrize(
    ("rotulo", "valor"),
    [
        ("40 digitos, o comprimento de um SHA-1", SHA256_DE_EXEMPLO[:40]),
        ("64 digitos em maiuscula", SHA256_DE_EXEMPLO.upper()),
        ("65 digitos", SHA256_DE_EXEMPLO + "a"),
    ],
)
def test_hexadecimal_que_nao_e_sha256_continua_sendo_pego(
    tmp_path: Path, rotulo: str, valor: str
) -> None:
    """Fronteira: a exclusão é estreita, não uma licença para hexadecimal.

    Os três casos são o MESMO valor liberado, alterado num eixo só: comprimento
    menor, caixa alta, comprimento maior. Se algum passar, o padrão deixou de
    estar ancorado e a exclusão virou outra coisa.

    Os três são derivados em tempo de execução, nunca escritos como literal.
    Um hexadecimal de 40 dígitos no fonte seria acusado neste próprio arquivo —
    corretamente, porque 40 dígitos é justamente o que a exclusão não cobre.
    """
    assert _acusa(f"valor: {valor}", tmp_path), f"deixou passar: {rotulo}"


def test_este_arquivo_nao_reprova_o_proprio_hook() -> None:
    """O arquivo que testa o detector é escaneado pelo detector.

    Fecha o laço: qualquer amostra escrita aqui como literal — um hash de outro
    comprimento, uma chave copiada de algum lugar — passa a falhar no pytest,
    com explicação, em vez de reprovar um commit lá na frente sem contexto.
    """
    assert not _acusa_arquivo(Path(__file__)), (
        "este arquivo tem uma amostra escrita como literal. Monte-a em tempo de "
        "execucao, como as outras, em vez de afrouxar a exclusao."
    )
