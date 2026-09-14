# ADR 0002 — Camada de adaptadores de modelo: LiteLLM ou implementação própria

- **Status:** Aceita
- **Data:** 2026-09-14
- **Decisores:** Rafael Machado Tavares
- **Substitui:** —
- **Relacionada a:** ADR 0001 (registro de decisões), ADR 0003 (sandbox)

## Contexto

O Curupira precisa chamar múltiplos provedores de modelo (Anthropic, OpenAI,
Google, xAI, e provedores de modelos abertos) com uma interface única, expondo:
mensagens, definição de ferramentas em JSON Schema, chamadas de ferramenta
retornadas, temperatura, seed, contagem de tokens e custo.

Duas opções: usar o `litellm` como camada de abstração, ou escrever adaptadores
próprios, um por provedor.

Em 24/03/2026 as versões 1.82.7 e 1.82.8 do `litellm` foram publicadas no PyPI
contendo um *credential stealer* de três estágios, após comprometimento provável
da conta PyPI de um mantenedor — com origem rastreada a uma vulnerabilidade no
Trivy usado no próprio workflow de segurança do CI/CD do projeto. A janela foi de
cerca de 5h30, entre 10:39 UTC e aproximadamente 16:00 UTC.

O código malicioso residia em `proxy_server.py` (ambas as versões) e em
`litellm_init.pth` (1.82.8). O payload enumerava o sistema, coletava credenciais
de SSH, Git, AWS, GCP, Azure, Kubernetes, Terraform e carteiras de criptomoeda, e
exfiltrava para domínios controlados pelos atacantes. A orientação pública foi
tratar as máquinas afetadas como comprometidas. O pacote `telnyx` caiu na mesma
campanha.

**O detalhe decisivo é o `.pth`.** Um arquivo `.pth` em `site-packages` é
executado pelo interpretador **em toda inicialização do Python**, independente de
qualquer `import`. Não era preciso importar o `litellm` para ser comprometido:
bastava ter o pacote instalado no ambiente e rodar qualquer script.

Isso reclassifica o risco. Não é "uma dependência que pode ter bug". É "uma
dependência cuja janela de comprometimento alcança todo processo Python do
ambiente, incluindo o processo do orquestrador que segura as chaves de API".

O projeto LiteLLM respondeu adequadamente: remoção dos pacotes, rotação de
credenciais de mantenedores, perícia com a Mandiant, CI/CD v2 com ambientes
isolados e portões de segurança mais fortes, e assinatura de imagens Docker com
cosign a partir da v1.83.0-nightly. Esta ADR não é um julgamento do projeto.

## Forças em jogo

1. **Confounding científico.** O Curupira mede como um agente se comporta diante
   de uma definição de ferramenta específica. Uma camada que normaliza schemas
   entre provedores altera os bytes que chegam ao modelo, de forma diferente por
   provedor. Se a camada traduz a descrição de ferramenta de um jeito para a
   Anthropic e de outro para a OpenAI, parte do que o Delta PT-BR mede é a
   camada, não o agente. O benchmark precisa saber exatamente o que foi enviado.
2. **Superfície de ataque.** O LiteLLM suporta cerca de 100 provedores e traz
   proxy, roteamento, cache, budget e observabilidade. Usaríamos uma fração
   ínfima disso e herdaríamos o risco de tudo, num processo que segura chaves.
3. **Reprodutibilidade.** A tupla de reprodutibilidade do projeto inclui a versão
   do adaptador. Fixar uma versão de um projeto com cadência de release quase
   diária significa ou congelar numa versão que acumula CVEs, ou mover a tupla
   com frequência.
4. **Custo de manutenção.** APIs de provedor mudam. O LiteLLM absorve essa
   manutenção de graça, e adicionar um provedor novo é configuração, não código.
   **Este é o argumento real a favor, e ele não é pequeno.**
5. **Escopo real da v0.1.** Seis modelos, sem streaming, sem proxy, sem
   roteamento. Cada adaptador é uma requisição HTTPS, um mapeamento de schema e um
   parser de resposta: 100 a 150 linhas, com teste de contrato.

## Opções consideradas

### Opção A — LiteLLM com versão pinada e hash no lockfile

- (+) Cobertura imediata de dezenas de provedores; manutenção terceirizada.
- (+) Pinagem por hash impede que uma versão maliciosa nova seja instalada.
- (+) Menos código nosso é menos bug nosso.
- (−) Não resolve o confounding científico da normalização de schema.
- (−) Herda a superfície inteira do pacote no processo que segura as chaves.
- (−) Pinar por hash protege contra a versão futura comprometida, mas obriga a
  uma decisão de atualização recorrente sob pressão de CVE.
- (−) O `.pth` demonstrou que o raio de alcance é o interpretador, não o import.

### Opção B — Adaptadores próprios, um por provedor

- (+) Sabemos exatamente quais bytes vão para o modelo. Requisito de medição, não
  preferência de estilo.
- (+) Superfície: `httpx` e `pydantic`, que já são dependências do núcleo.
- (+) A versão do adaptador é nossa, versionada junto com o benchmark; a tupla de
  reprodutibilidade fica estável.
- (+) O corpo de requisição literal pode ser gravado no resultado, o que torna
  uma rodada auditável por terceiros.
- (−) Manutenção nossa quando um provedor muda a API.
- (−) Adicionar um provedor novo custa código e teste, não configuração.
- (−) Reimplementamos retry, backoff e parsing de erro — resolvido, mas nosso.

## Decisão

**Opção B.** Adaptadores próprios, um por provedor, sem `litellm` no núcleo.

O argumento decisivo não é segurança — é medição. Um benchmark que não controla o
que envia ao modelo não pode atribuir a diferença medida ao modelo. O incidente
de março/2026 é o segundo argumento, não o primeiro: **se o LiteLLM nunca tivesse
sido comprometido, a decisão seria a mesma por causa do confounding.**

Consequência prática: `litellm` não entra em `dependencies` nem em nenhum extra do
`pyproject.toml`, da v0.1 à v1.0. `tests/test_esqueleto.py` fixa isso em teste.

## Postura de supply chain (vale independentemente desta decisão)

1. **Lockfile com hash.** Toda dependência fixada por versão e por hash
   (`uv.lock`, ou `requirements.txt` com `--require-hashes`). Instalação sem hash
   é erro de build.
2. **Janela de carência de 7 dias.** Nenhuma release com menos de 7 dias entra no
   lockfile. As versões maliciosas do `litellm` viveram cerca de 5h30. Uma
   carência de 7 dias as teria bloqueado com duas ordens de grandeza de folga.
   **É a mitigação de melhor retorno desta lista inteira.**
3. **`pip-audit` bloqueante no CI**, e CodeQL habilitado.
4. **O job que instala dependências nunca recebe secret.** Lint, teste e auditoria
   rodam sem chave; o job que roda o benchmark recebe chave e não instala nada que
   não esteja no lockfile já auditado.
5. **Nunca usar `pull_request_target` com secrets.** PR de fork não vê chave.
6. **Ambiente de desenvolvimento é descartável.** Venv por projeto, jamais global.

## Consequências

- **Positivas:** superfície mínima; bytes auditáveis; tupla de reprodutibilidade
  estável; o corpo da requisição vira artefato da rodada.
- **Negativas:** cobertura de provedores limitada ao que escrevermos. Um
  contribuidor que queira pontuar um provedor exótico precisa escrever um
  adaptador. Retry, backoff e parsing de erro são manutenção nossa.
- **Revisitar se:** o número de provedores pedidos pela comunidade passar de cerca
  de 12, ou se surgir uma camada de abstração minimalista, auditável e com
  *trusted publishing* verificável. Nesse caso, a reabertura é uma ADR nova, e a
  decisão terá que enfrentar o argumento do confounding, não só o de segurança.

## Referências

- Security Update: Suspected Supply Chain Incident — LiteLLM
  <https://docs.litellm.ai/blog/security-update-march-2026>
- Compromised litellm PyPI Package Delivers Multi-Stage Credential Stealer —
  Sonatype
  <https://www.sonatype.com/blog/compromised-litellm-pypi-package-delivers-multi-stage-credential-stealer>
- LiteLLM and Telnyx compromised on PyPI: the TeamPCP supply chain campaign —
  Datadog Security Labs
  <https://securitylabs.datadoghq.com/articles/litellm-compromised-pypi-teampcp-supply-chain-campaign/>
