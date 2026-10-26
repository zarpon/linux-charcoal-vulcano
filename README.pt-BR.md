# Charcoal SteamOS Kernel — canal estável

[English](README.md)

A `master` compila o kernel Charcoal para o **SteamOS stable atual**. O SteamOS 3.9 estável usa atualmente Linux 7.2; são versões diferentes. A pilha completa mantida na `kernel-7.2` substitui o fluxo antigo de kernel 6.18 na `master`.

## Instalação da Latest

Atualize o SteamOS stable e execute no Modo Desktop. No Steam Deck, habilite IOMMU na BIOS e reinicie antes.

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/master/install-charcoal.sh -o install-charcoal.sh && bash install-charcoal.sh
```

O instalador consulta [releases/latest](https://github.com/zarpon/linux-charcoal-vulcano/releases/latest), rejeitando rascunhos, prereleases e tags Preview. Aceita uma tag estável `charcoal-<versão do pacote>-r<execução>`, exatamente um ZIP `linux-charcoal-<série>-*.zip` e `RELEASE-ZIP-SHA256SUM`. Os pacotes acompanham a série detectada: atualmente `linux-charcoal-72` e `linux-charcoal-72-headers`, com sufixo correspondente nas futuras séries.

Antes de alterar pacotes, verifica o SHA-256 do ZIP, extrai com segurança exatamente o par kernel/headers da mesma série, confere seus hashes e consulta metadados com pacman. `pacman -Qp` verifica metadados, sem simular integralmente a transação ou o espaço disponível.

Identifica pacotes anteriores `linux-charcoal*` e o kernel original/headers conflitantes da série selecionada. A remoção do kernel original exige confirmação explícita; pacotes não relacionados ficam fora da lista. Após confirmar a transação, libera escrita e modo de desenvolvimento, remove os pacotes aprovados com `pacman -Rdd`, instala o par verificado, reaplica o perfil persistente de swap e atualiza o GRUB. Restaura o modo somente leitura ao sair e nunca reinicia automaticamente.

Prepara cópias exatas do cache `/var/cache/pacman/pkg` para rollback. Se a instalação falhar e todos os pacotes removidos estavam no cache, tenta restaurá-los. Sem o cache completo, não há garantia de rollback automático: corrija a instalação do kernel antes de reiniciar. Mantenha um método de recuperação do SteamOS disponível.

As opções existentes continuam compatíveis: `CHARCOAL_72_REMOVE_STOCK=1` autoriza explicitamente a remoção do original e `CHARCOAL_72_ASSUME_YES=1` aceita as duas confirmações. Os nomes antigos são preservados entre séries.

Após o sucesso, reinicie manualmente e confira `uname -r` e `pacman -Q | grep '^linux-charcoal'`. O kernel deve conter o sufixo Charcoal instalado. Use com o SteamOS stable atual, não com uma imagem antiga sem suporte.

## Acompanhamento automático do stable

A referência é o [manifesto oficial de atualização stable](https://steamdeck-atomupd.steamos.cloud/meta/holo/steamos/amd64/steamdeck/stable.json) da Valve, não o maior número encontrado em um índice de fontes. `automation/prepare-steamos-stable.py`:

1. Seleciona uma imagem explicitamente marcada `stable`, com versão do SteamOS e build ID.
2. Busca o `.manifest.pacman` daquela imagem exata no servidor oficial.
3. Identifica o pacote e a versão exatos de `linux-neptune-<série>` entregues na imagem.
4. Deriva o repositório pela versão principal/secundária do SteamOS: 3.9 usa `jupiter-3.9`; 3.10 passa automaticamente para `jupiter-3.10`.
5. Exige o arquivo-fonte exato, resolve a tag Valve, busca sua configuração Arch/Valve e atualiza nomes dos pacotes e série-alvo dos patches.

Assim, a mudança do stable para Linux 7.3 ou superior é descoberta automaticamente, inclusive quando muda o repositório do SteamOS. Imagens preview/main e kernels RC/beta são rejeitados. Metadados ausentes ou ambíguos fazem o build falhar, sem fallback silencioso para main ou uma fonte antiga. Imagem, URLs do manifesto e da fonte, tag e série ficam em `steamos-stable-source.json`.

Descobrir um kernel novo não pula a compatibilidade dos patches. Todas as famílias continuam obrigatórias. O resolvedor escolhe primeiro a versão mais recente de cada projeto e prefere sua variante nativa da série detectada; portes/adaptadores mantêm hashes e origem. Os portes existentes passam por verificação contra a nova fonte antes da compilação. Se os bytes upstream ou APIs mudarem de forma incompatível, o build falha para correção, sem retirar patches, escolher uma versão antiga do projeto ou publicar um kernel incompleto. Consulte [PATCH-SOURCES.md](PATCH-SOURCES.md).

A pilha preserva BORE/coexistência sched_ext, POC Selector, ADIOS/elevator padrão, LRU Marie, NAP, ZRAM-IR, AMD P-State EPP boost, otimizações CPU/O3, Clear/Zen, compatibilidade DKMS/Clang/Polly, firmware/wireless, Ryzen SMU, drivers de controles e patches locais Van Gogh/IOMMU. A ordem de aplicação é mantida. `6.16.12-bore-6.8.0-final.patch` permanece como referência de compatibilidade; o BORE atual é selecionado dinamicamente. Os arquivos 6.18 substituídos dão lugar às implementações 7.2 mantidas.

Funcionalidades já presentes na fonte Valve continuam contabilizadas pelo resolvedor, sem reaplicação duplicada. Patches antigos fsync opcode-31, C23/libbpf, Bluetooth SSP e Qualcomm ath11k upstream já ausentes da `kernel-7.2` não são reintroduzidos. O `patch-lock.json` validado registra versões, origens, hashes e funcionalidades atendidas pelo upstream.

## Compilação e publicação

[push.yml](.github/workflows/push.yml) compila e publica em pushes da `master`. Pull requests e builds de `validation/**` não publicam. O disparo manual aceita `publish_release=false` para gerar somente artefatos. A execução diária ocorre às **03:05 UTC / 00:05 de Brasília**, disparando somente a `master`.

Releases estáveis usam `draft = false`, `prerelease = false`, `latest = true`. Criação e atualização marcam Latest explicitamente. Resolução das fontes, validação da política/lock, checksums, preparação dos patches, configuração, compilação e empacotamento precisam passar antes. Depois o workflow relê flags, assets e `/releases/latest`; falha de publicação ou leitura faz a execução falhar. Releases históricas são preservadas.

Os assets incluem kernel/headers, ZIP, checksums, lock de patches e metadados da fonte estável. As notas vêm do lock validado daquele build. O ZIP também contém lock, metadados e auditoria de checksums.

A `kernel-7.2` permanece apenas para builds manuais de desenvolvimento. [build-kernel-7.2.yml](.github/workflows/build-kernel-7.2.yml) não tem gatilho push/schedule nem publicação de releases; disponibiliza artefatos. Não recebe mais o disparo diário.

Preparação local com Python 3, Bash e Git:

```bash
python3 automation/prepare-pkgbuild-7.2.py --write PKGBUILD
python3 automation/prepare-steamos-stable.py --fetch-config
python3 automation/resolve-controller-drivers.py --write
python3 automation/resolve-latest-patches-7.2-policy.py --overrides logs/patch-source-overrides-stable.json --write
python3 automation/validate-patch-lock.py --manifest logs/patch-sources-7.2.json --overrides logs/patch-source-overrides-stable.json
```

Alguns nomes de helpers mantêm `7.2` por compatibilidade; a entrada stable fornece a série detectada dinamicamente. O Dockerfile fornece Arch Linux/LLVM. O workflow finaliza checksums dos bytes resolvidos, verifica fontes, prepara patches e compila com makepkg. Testes estáticos não substituem boot no hardware de destino.

## Recursos de execução preservados

O3 e o perfil de jogos/memória Charcoal continuam ativos. A instalação desabilita persistentemente ZRAM/serviços, habilita ZSTD zswap com pool de **35% da RAM**, shrinker ativo e swapfile em `/home` com **75% da RAM**. O suporte ZRAM-IR permanece disponível no kernel. Consulte [SWAP.md](SWAP.md).

Permanecem `vm.vfs_cache_pressure=100`, `vm.dirty_background_ratio=2` e `vm.dirty_ratio=5`, preservando os padrões do LRU Marie. `CONFIG_ZEN_INTERACTIVE` controla os ajustes existentes de RCU assíncrono evdev e seleção schedutil P-State, sem importar outros padrões Zen de memória/scheduler.

IOMMU PerfOpt usa automaticamente o caminho DMA identity otimizado em GPUs integradas AMD elegíveis. Enquanto ativo, pula ATS, PRI, PASID e SVA/GCR3 naquele dispositivo, reduzindo contenção DMA. O resultado depende de hardware/carga; não há ganho percentual garantido nem opção de desativação em execução `amdgpu.iommu_perfopt`.

Cada build busca as ferramentas NAP mais recentes e registra commit/hashes. O aprendizado persiste entre reinicializações, com salvamento a cada 30 minutos. Inclui `napctl` e `/usr/share/nap/napviz.html`, gerado a partir do modelo do kernel compilado. Consulte [NAP-TOOLS.md](NAP-TOOLS.md).
