# Política de fontes e compatibilidade

A entrada `automation/prepare-steamos-stable.py` consulta o canal stable oficial da Valve, identifica o kernel na lista de pacotes da imagem e deriva o índice de fontes pela versão do SteamOS. SteamOS 3.9 usa `jupiter-3.9`; 3.10 usa automaticamente `jupiter-3.10`. Não escolhemos uma série só por ela aparecer em main ou no índice de fontes.

`automation/patch-sources.json` declara todas as famílias de patches. A política gerada em `logs/patch-source-overrides-stable.json` utiliza a série detectada, preservando as famílias, os portes e os hashes de origem. Os nomes históricos de alguns helpers mantêm `7.2`, sem fixar a descoberta do stable nessa versão.

O resolvedor identifica primeiro a versão mais recente de cada projeto upstream. Prefere a variante nativa dessa versão para a série detectada. Quando precisa de um porte local, exige versão/hash upstream exatos; mudança desses bytes interrompe o build para revisão. Adaptadores validam a estrutura esperada e a preparação confere a aplicação contra a árvore real antes da compilação. Uma nova série pode exigir correção dos portes; não removemos patches para concluir um build.

Fontes de commit único ou listas de discussão são registradas por seus bytes exatos. MBOX/MIME é decodificado antes do hash e aplicação. A série AMD P-State EPP boost mantém quatro componentes independentes. Fontes já incorporadas pela Valve são contabilizadas pelo resolvedor, sem duplicação funcional.

`logs/patch-lock.json` registra versões, commits, caminhos, URLs, origens, SHA-256 e tamanho de componentes principais e auxiliares. `logs/steamos-stable-source.json` registra a imagem stable e a fonte exata. O build valida ambos antes de publicar a Latest.

Patches locais Van Gogh e IOMMU permanecem versionados. O antigo overlay BORE 6.16 é preservado como referência de compatibilidade; não substitui a seleção do BORE upstream atual. As implementações 6.18 substituídas foram removidas da árvore corrente e continuam recuperáveis no histórico Git.
