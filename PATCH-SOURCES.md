# Política de fontes de patches

Cada build resolve novamente as fontes remotas antes de executar `makepkg`.

- `automation/patch-sources.json` declara todos os patches remotos aplicados pelo `PKGBUILD`.
- Fontes GitHub são lidas da ponta atual da branch oficial. Para cada componente versionado, o resolvedor começa pela release mais nova, prioriza seu patch nativo para Linux 6.18 e só considera uma porta quando não existe patch nativo aplicável.
- O payload upstream mais novo é sempre a primeira tentativa de aplicação. Uma porta local da série 6.18 só é aceita como fallback estrito após falha dessa tentativa e deve estar vinculada à mesma versão e ao SHA-256 canônico do upstream. Antes de qualquer uso, a porta é verificada com `git apply --check` contra a árvore Valve exata selecionada; assim uma nova revisão 6.18.x não é bloqueada apenas por metadados de versão, mas uma porta que não se aplica continua bloqueando o empacotamento. O POC Selector é uma exceção controlada: o adaptador `poc-selector-valve` usa diretamente os bytes upstream atuais, registra commit/caminho/SHA-256 no lock e só aceita os hunks conhecidos de `rq::poc_idle_committed` e `select_idle_sibling()`. Ele gera um patch Valve/BORE atômico, verifica-o com `git apply --check` e só então altera a árvore; uma mudança estrutural é bloqueada antes do empacotamento.
- Patches de commit único ou listas de discussão não possuem uma linha de versões; seus bytes atuais são baixados, validados e registrados no lock. Mensagens de listas são decodificadas de MBOX/MIME para o payload canônico do patch antes do hash e da aplicação, evitando que codificação quoted-printable ou cabeçalhos de transporte alterem o patch aplicado.
- A série RFC de quatro patches `amd_pstate_epp_boost` aplica primeiro seus payloads `linux-pm` canônicos mais recentes e mantém quatro portas locais separadas para SteamOS 6.18 apenas como fallback. Cada porta é vinculada ao SHA-256 do payload canônico; se qualquer mensagem upstream mudar, o resolvedor falha antes do `makepkg`. A aplicação contra a árvore Valve exata é verificada em toda build.
- `logs/patch-lock.json` registra commit, caminho, URL, origem, SHA-256 e tamanho de todas as fontes principais e auxiliares.
- O workflow `patch-source-policy.yml` impede a inclusão de um patch remoto no `PKGBUILD` sem cobertura pelo manifesto.

Patches exclusivamente locais, como os ajustes Vangogh, não possuem upstream versionado e permanecem sob controle de versão neste repositório.
