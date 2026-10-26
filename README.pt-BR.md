# Charcoal — branch manual de desenvolvimento Linux 7.2

A linha estável mantida agora é a [`master`](https://github.com/zarpon/linux-charcoal-vulcano/tree/master). O SteamOS 3.9 stable utiliza Linux 7.2; as versões identificam projetos diferentes.

Esta branch não publica mais releases ou prereleases e não tem build automático por push ou diário. O workflow `Build SteamOS 7.2 development kernel manually` pode ser disparado manualmente na `kernel-7.2` para disponibilizar somente artefatos do Actions. As antigas releases Preview são preservadas, sem novas publicações. Os nomes dos artefatos podem manter a identificação Preview histórica.

## Instalação estável

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/master/install-charcoal.sh -o install-charcoal.sh && bash install-charcoal.sh
```

O instalador desta branch também acompanha `releases/latest`, aceitando releases estáveis com `prerelease = false`. Rejeita tags Preview antigas, confere os SHA-256 do ZIP e do par kernel/headers, exige confirmação para substituir pacotes conflitantes, preserva rollback por arquivos exatos do cache quando disponíveis, restaura o modo somente leitura e não reinicia automaticamente. No Steam Deck, habilite IOMMU na BIOS antes.

A master identifica automaticamente a imagem do SteamOS stable, seu kernel exato e o repositório de fontes correspondente, inclusive em futuras mudanças para SteamOS 3.10 / Linux 7.3. Consulte a [README estável](https://github.com/zarpon/linux-charcoal-vulcano/blob/master/README.pt-BR.md) para política, instalação e limites da recuperação. Os comandos locais daquele documento são para a `master`; esta branch usa o workflow manual dedicado 7.2.

## Recursos de desenvolvimento preservados

Nenhum patch de kernel ou recurso de execução foi retirado desta branch. Mantém BORE/coexistência sched_ext, POC Selector, ADIOS, LRU Marie, NAP, ZRAM-IR, AMD P-State, otimizações CPU, compatibilidade LLVM/Polly, drivers de controles, Ryzen SMU, Van Gogh e IOMMU, com a política de seleção de fontes existente.

Permanecem O3, ZSTD zswap (pool de 35% RAM e shrinker ativo), desativação persistente do ZRAM e swapfile em `/home` com 75% RAM. Mantém `vm.vfs_cache_pressure=100`, `vm.dirty_background_ratio=2`, `vm.dirty_ratio=5` e os padrões próprios do LRU Marie. Ferramentas e persistência do aprendizado NAP continuam disponíveis. Consulte [SWAP.md](SWAP.md) e [NAP-TOOLS.md](NAP-TOOLS.md).

IOMMU PerfOpt mantém o caminho DMA identity existente em GPUs integradas AMD elegíveis e as mesmas implicações ATS/PRI/PASID/SVA. Não há ganho percentual garantido.
