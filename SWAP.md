# Zswap e swapfile na partição home

A instalação usa `zswap.enabled=1`, `zswap.max_pool_percent=50`,
`zswap.shrinker_enabled=1`, `zswap.compressor=lz4` e allocator `zsmalloc`.
O argumento `zswap.zpool=zsmalloc` é preservado para kernels antigos; os
atuais já usam zsmalloc diretamente e não oferecem esse seletor por sysfs.

O pacote cria `/home/.gaming-swap/swapfile` na partição que contém `/home`,
com 150% de `MemTotal`, arredondado para páginas inteiras. O diretório é
exclusivo de root (0700) e o arquivo tem permissão 0600. Em Btrfs, usa um
subvolume separado e `btrfs filesystem mkswapfile`, sem CoW nem buracos,
validando o mapeamento antes do `swapon`. Também suporta ext4 e XFS.

O arquivo novo é ativado antes de drenar e remover os swapfiles anteriores.
Eles são identificados pelos swaps ativos, fstab, unidades de swap e caminhos
convencionais. Arquivos sem assinatura de swap não são apagados. Partições
de swap são preservadas. Espaço insuficiente, layout Btrfs inválido ou falha
de `swapoff` interrompem a migração e preservam os arquivos antigos.
A criação requer espaço para o novo arquivo mais 1 GiB de reserva, além do
swap antigo ainda existente. Atualizações reutilizam o arquivo com o tamanho
correto; uma mudança na RAM cria outro nome dentro do mesmo diretório.

A persistência usa `/etc/fstab`, parâmetros do GRUB, modprobe, desativação do
zram-generator e máscaras dos serviços zram detectados, incluindo SteamOS.
`gaming-zswap.service` reaplica os parâmetros por sysfs em cada boot.
As configurações próprias do LRU Marie são preservadas. A migração ocorre
no sistema instalado, nunca no ambiente de compilação do pacote.

As configurações persistem entre reinícios e reinstalações do kernel.
Uma atualização de imagem SteamOS que substitua configurações ou pacotes
exige reinstalar o kernel/tuning. O script não configura hibernação.

Após reiniciar, confira:

```bash
swapon --show
cat /sys/module/zswap/parameters/{enabled,max_pool_percent,shrinker_enabled,compressor}
systemctl status gaming-zswap.service
```

`swapon --show` deve listar o arquivo em `/home/.gaming-swap` e não listar
`/dev/zram*`. Os parâmetros devem mostrar `Y`, `50`, `Y` e `lz4`.
Se a instalação falhar, corrija o erro indicado e execute novamente:

```bash
sudo /usr/lib/gaming-swap/configure
```
