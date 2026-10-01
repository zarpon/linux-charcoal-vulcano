# Kernel Charcoal SteamOS — SteamOS 7.2 Preview

Esta branch é a linha experimental do Charcoal para o **SteamOS 7.2**. Ela fica isolada da linha estável `master`/6.18 e das demais linhas de kernel do repositório.

> **Importante:** os builds produzidos pela `kernel-7.2` usam um canal próprio de releases chamado **Charcoal 7.2 Preview**. Todo build concluído com sucesso nessa branch é publicado como **pré-release** do GitHub e nunca como `Latest`, sem assumir o canal de release estável do repositório.

## Política de fonte

O build localiza automaticamente o pacote-fonte oficial mais recente `linux-neptune-72` no índice público de pacotes do SteamOS, converte essa versão para a tag correspondente da série 7.2 no `linux-integration` da Valve e então resolve toda a pilha de patches do Charcoal para essa fonte.

Para cada família de patch mantida pelo projeto, a regra é:

1. selecionar primeiro a **versão mais nova do projeto upstream**;
2. dentro dessa versão, preferir uma variante nativa para kernel/SteamOS 7.2 quando existir;
3. se a versão mais nova não possuir variante utilizável para 7.2, utilizar um porte revisado e rastreado dessa mesma versão, em vez de retroceder silenciosamente para uma versão antiga do patch apenas porque ela aplica sem conflitos.

O pacote-fonte exato da Valve, tag, commit, origem de cada patch, versão upstream selecionada e SHA-256 ficam registrados nos logs da compilação e no `patch-lock.json`. Portes locais ficam vinculados aos bytes exatos do patch upstream que implementam; se o upstream mudar, a validação exige revisão/novo porte em vez de reutilizar silenciosamente código desatualizado.

## Instalar o Charcoal 7.2 Preview

Execute no Modo Desktop do SteamOS:
> **Requisito de BIOS no Steam Deck:** antes de instalar, confirme que a opção
> IOMMU está ativa na BIOS. Salve a configuração e reinicie.

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/kernel-7.2/install-charcoal.sh -o install-charcoal-7.2.sh && bash install-charcoal-7.2.sh
```

O instalador fica preso exclusivamente ao canal 7.2 Preview. Ele consulta a lista de Releases do GitHub e seleciona o pré-release publicado mais recente cuja tag comece com `charcoal-7.2-preview-`, rejeitando drafts e releases comuns.

O instalador **não usa `releases/latest`**. Portanto, a instalação do 7.2 Preview não depende de qual release de outra branch esteja marcado como `Latest` no repositório.

Somente é aceito um bundle `linux-charcoal-72-*.zip` acompanhado do arquivo `RELEASE-ZIP-SHA256SUM`.

Antes de alterar qualquer pacote do sistema, o instalador:

- baixa completamente o bundle 7.2 Preview;
- valida o SHA-256 do ZIP da release;
- valida o SHA-256 dos dois pacotes internos, kernel `linux-charcoal-72` e headers;
- faz um preflight dos pacotes validados com o pacman;
- detecta os pacotes instalados cujo nome começa com `linux-charcoal`;
- exibe a transação e exige confirmação antes de tornar o SteamOS gravável.

Somente depois dessas validações e da confirmação, qualquer kernel Charcoal anterior é removido com uma transação restrita `pacman -Rdd`, e em seguida são instalados o kernel e os headers SteamOS 7.2 previamente verificados. Pacotes como `linux-neptune-*` e quaisquer pacotes não relacionados nunca entram na lista de remoção. O `-Rdd` é usado especificamente para impedir remoção em cascata de dependências.

Se os arquivos exatos dos pacotes Charcoal anteriores ainda existirem em `/var/cache/pacman/pkg`, o instalador os copia para a área temporária antes da remoção e tenta restaurá-los automaticamente caso a instalação dos novos pacotes 7.2 falhe. Se não houver material de rollback disponível e a instalação falhar após a remoção, o instalador interrompe o procedimento, avisa para **não reiniciar** e restaura o sistema de arquivos raiz do SteamOS para modo somente leitura.

O instalador nunca reinicia o aparelho automaticamente. Depois de uma instalação concluída com sucesso, reinicie manualmente e confirme:

```bash
uname -r
```

O resultado deve conter `charcoal-72`.

## Política de releases desta branch

Todo build de kernel concluído com sucesso na branch `kernel-7.2` é empacotado em ZIP, recebe metadados SHA-256 e é publicado no canal dedicado com:

- título: **Charcoal 7.2 Preview**;
- prefixo exclusivo de tag: `charcoal-7.2-preview-`;
- `prerelease = true`;
- `latest = false`.

Assim, o kernel 7.2 fica no canal de pré-releases para teste sem disputar o `Latest` estável usado pelas outras linhas do repositório.

A branch temporária de validação pode executar testes, resolver fontes, aplicar patches, compilar e gerar artifacts, mas **não publica releases**. A publicação do pré-release só ocorre quando o código está na branch definitiva `kernel-7.2` e a compilação completa termina com sucesso.

## Configuração atual do kernel 7.2

A branch 7.2 mantém as configurações de jogos e memória do Charcoal, incluindo o porte específico do zram-ir para 7.2. A política esperada de ZRAM continua sendo LZ4 como compressor primário e ZSTD como recompressor de prioridade 1, com o nível equivalente a `zstd --fast=1` definido no próprio porte do kernel.

### AMD IOMMU PerfOpt

Em IOMMU AMD compatível, o PerfOpt é habilitado automaticamente para GPUs
integradas elegíveis usando um domínio DMA identity. O caminho otimizado do IOMMU
pode reduzir a latência de DMA. A configuração de ATS, PRI, PASID
e SVA/GCR3 é ignorada para esse dispositivo enquanto o PerfOpt está ativo,
reduzindo o isolamento de DMA do IOMMU nesse caminho. O efeito depende do hardware
e da carga; não há percentual de ganho garantido. Não há opção
amdgpu.iommu_perfopt para desativá-lo em tempo de execução.

## Workflow de build

O workflow dedicado é:

`.github/workflows/build-kernel-7.2.yml`

A compilação executa a resolução dinâmica da fonte oficial do SteamOS 7.2, auditoria das versões upstream dos patches, validação do `patch-lock`, preflight/aplicação no código-fonte real e compilação do kernel. Somente depois de todas essas etapas concluídas com sucesso a branch definitiva `kernel-7.2` pode publicar o **Charcoal 7.2 Preview**.

O próprio workflow verifica após a publicação que o release não é draft, é prerelease e não está marcado como `Latest`. Uma falha de publicação ou de validação faz o workflow falhar.

## Aviso

O suporte ao SteamOS 7.2 desta branch é experimental. Use este instalador apenas se a intenção for testar a linha **Charcoal 7.2 Preview** e se houver conhecimento de como restaurar o kernel stock do SteamOS em caso de necessidade.

Para a linha estável do Charcoal, utilize a branch `master`.
