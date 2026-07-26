# Política de fontes de patches

Cada build resolve novamente as fontes remotas antes de executar `makepkg`.

- `automation/patch-sources.json` declara todos os patches remotos aplicados pelo `PKGBUILD`.
- Fontes GitHub são lidas da ponta atual da branch oficial e selecionadas por compatibilidade com Linux 6.16 e, quando disponível, pela versão do projeto.
- O componente `zram-ir` acompanha a família oficial de recompressão imediata, enquanto o componente `lz4kdr` acompanha separadamente o backend LZ4KDR. Para cada componente, o resolvedor primeiro seleciona a versão compatível mais nova com `6.16.12`; na ausência dela, seleciona a versão de kernel mais próxima e valida o porte local antes da compilação.
- Patches com porta local continuam consultando o upstream atual. Uma alteração de versão ou do SHA-256 aprovado interrompe o build até que a porta seja atualizada e validada.
- Patches de commit único ou listas de discussão não possuem uma linha de versões; seus bytes atuais são baixados, validados e registrados no lock.
- `logs/patch-lock.json` registra commit, caminho, URL, origem, SHA-256 e tamanho de todas as fontes principais e auxiliares.
- O workflow `patch-source-policy.yml` impede a inclusão de um patch remoto no `PKGBUILD` sem cobertura pelo manifesto.

Patches exclusivamente locais, como os ajustes Vangogh, não possuem upstream versionado e permanecem sob controle de versão neste repositório.
