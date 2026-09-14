# Política de segurança do Curupira

## 1. Reportar uma vulnerabilidade no código

Use o canal privado de *security advisory* do GitHub neste repositório.
Não abra issue pública para vulnerabilidade.

Prazo de resposta pretendido: **5 dias úteis** para acusar recebimento.

## 2. Reportar colisão de dado sintético com pessoa real

Todo identificador do dataset (CPF, CNPJ, CEP, telefone, placa, chave PIX, linha
digitável, chave NF-e) é gerado proceduralmente pelos algoritmos públicos de
formação e dígito verificador. Nenhum foi copiado de ninguém.

Ainda assim: o espaço de CPF é da ordem de 10⁹ combinações e o Brasil tem mais de
200 milhões emitidos. **Colisão aritmética é inevitável e não é evitável por
engenhosidade de geração.** O que o projeto evita é a *identificação*: nenhum
registro sintético combina nome completo + CPF válido + endereço, e data de
nascimento não existe no dataset.

### Como reportar

Abra uma issue com o rótulo `privacidade`, informando **apenas**:

- o `task_id`, e
- o valor incriminado (que já é público no repositório).

**Não envie o seu documento, nem o seu CPF, nem comprovante.** Pedir dado pessoal
real para confirmar um dado sintético seria o erro que este procedimento existe
para impedir. Não avaliamos o mérito do pedido: **reportou, regeneramos.**

### O que acontece depois

1. Acuse de recebimento em até 5 dias úteis.
2. O registro é regerado com nova seed.
3. `task_version` sobe; a tarefa antiga entra na **errata** da suíte congelada.
4. Uma linha é adicionada em `CHANGELOG-PRIVACIDADE.md` dizendo qual *classe* de
   campo foi regerada — **sem repetir o valor**.
5. A revisão do dataset no Hugging Face é republicada.

> **Limitação conhecida, declarada:** o repositório de dataset do Hugging Face é
> um repositório git e o histórico é público. Regerar na ponta não apaga a
> revisão antiga. Antes da v0.1 ir ao ar, o procedimento de reescrita de
> histórico será testado uma vez num repositório descartável. Um procedimento de
> retirada que nunca foi executado não é um procedimento.

## 3. Trilha T5 — payloads de prompt injection

A T5 armazena payloads de prompt injection em repositório público.

### Por que publicamos

**O argumento principal: os payloads são inertes por construção.** Todo payload
ataca ferramentas falsas num mundo falso. `criar_transferencia` não move dinheiro
— acrescenta uma linha num JSON descartável. Nenhum payload contém endpoint real,
credencial real, URL que funcione ou instrução para exfiltrar dado que exista.
Um payload que só é perigoso dentro do nosso sandbox não é arsenal, é fixture.

Além disso, a norma do campo é a publicação aberta com declaração de ética:
JailbreakBench, AgentDojo, InjecAgent, BIPIA, CyberSecEval, HarmBench e AdvBench
publicam seus payloads abertamente.

### Onde o nosso caso é diferente — e o que fazemos a respeito

A hipótese de pesquisa da T5 é que os guardrails são mais frágeis em português.
Se confirmada, estaremos publicando ataques que são, por hipótese, **mais
eficazes** que os já públicos em inglês, num idioma sem corpus abundante de
injection. O argumento "já está disponível" é mais fraco para nós. Isso não muda
a decisão de publicar; muda o processo:

1. **Janela de notificação prévia de 90 dias.** Antes da divulgação pública da
   T5, resultados e payloads são enviados aos provedores cujos modelos foram
   testados, pelos canais de segurança oficiais.
2. **Divisão por potência, não por sorteio.** A taxonomia completa e um exemplar
   representativo de cada classe vão para o repositório público. A instância mais
   eficaz de cada classe vai para o **held-out privado**.
3. **Descoberta nova é vulnerabilidade, não tarefa.** Se ao montar a T5
   descobrirmos um ataque novo e sério contra um modelo em produção, ele vai
   primeiro ao provedor, sob embargo, pelo canal dele. Entra no dataset depois da
   correção ou do fim do embargo, o que vier primeiro.

### O que rejeitamos, e por quê

- **Gating do dataset no Hugging Face.** Teatro. Um formulário de dez segundos
  não detém ninguém mal-intencionado e atrapalha reprodutibilidade e revisão por
  pares. Se o conteúdo fosse perigoso demais para publicar, gating não
  resolveria; como não é, gating só prejudica.
- **Criptografar payloads no repositório público.** Blob criptografado em
  repositório público é convite.
- **Publicar sem notificação prévia.** Perderia, de graça, a única coisa que
  distingue divulgação responsável de divulgação.

## 4. Chaves de API

Seis barreiras técnicas, descritas na ADR 0003. Resumo:

| # | Barreira | Mecanismo |
|---|---|---|
| 1 | Não entra no repositório | `detect-secrets` no pre-commit + push protection do GitHub |
| 2 | Não entra no processo errado | Separação de privilégio: quem tem chave não executa, quem executa não tem chave |
| 3 | Não entra em log | `SecretStr` + `SecretRedactingFilter` que redige por valor |
| 4 | Não entra no resultado | `RunResult` é modelo fechado (`extra="forbid"`) |
| 5 | Não entra no cache | Chave do cache é hash; valor é só o corpo da resposta |
| 6 | **O teste que prova as barreiras 3, 4 e 5** | `tests/test_segredos.py` — canário de segredo |

Regras de CI:

- O job que instala dependências **nunca** recebe secret.
- PR de fork **nunca** recebe secret. Gatilho `pull_request`, **jamais**
  `pull_request_target`.

## 5. Supply chain

Ver **ADR 0002**. Resumo:

- Toda dependência fixada por versão **e** por hash. Instalação sem hash é erro
  de build.
- **Janela de carência de 7 dias**: nenhuma release com menos de 7 dias entra no
  lockfile. As versões maliciosas do `litellm` (24/03/2026) viveram cerca de
  5h30; uma carência de 7 dias as teria bloqueado com duas ordens de grandeza de
  folga.
- `pip-audit` bloqueante no CI; CodeQL habilitado; Dependabot ativo.
- `litellm` não é dependência deste projeto, nem como extra.
