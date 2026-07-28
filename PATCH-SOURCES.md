# Política de fontes de patches

Cada build resolve novamente as fontes remotas antes de executar `makepkg`.

- `automation/patch-sources.json` declara todos os patches remotos aplicados pelo `PKGBUILD`.
- Fontes GitHub são lidas da ponta atual da branch oficial e selecionadas por compatibilidade com Linux 6.16 e, quando disponível, pela versão do projeto.
- Portas locais estáticas continuam consultando o upstream atual. Uma alteração de versão ou do SHA-256 aprovado interrompe o build até que a porta seja atualizada e validada. O POC Selector é uma exceção controlada: o adaptador `poc-selector-valve` usa diretamente os bytes upstream atuais, registra commit/caminho/SHA-256 no lock e só aceita os hunks conhecidos de `rq::poc_idle_committed` e `select_idle_sibling()`. Ele gera um patch Valve/BORE atômico, verifica-o com `git apply --check` e só então altera a árvore; uma mudança estrutural é bloqueada antes do empacotamento.
- Patches de commit único ou listas de discussão não possuem uma linha de versões; seus bytes atuais são baixados, validados e registrados no lock.
- `logs/patch-lock.json` registra commit, caminho, URL, origem, SHA-256 e tamanho de todas as fontes principais e auxiliares.
- O workflow `patch-source-policy.yml` impede a inclusão de um patch remoto no `PKGBUILD` sem cobertura pelo manifesto.

Patches exclusivamente locais, como os ajustes Vangogh, não possuem upstream versionado e permanecem sob controle de versão neste repositório.
