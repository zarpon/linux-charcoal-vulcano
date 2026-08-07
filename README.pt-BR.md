# Kernel Charcoal SteamOS — branch SteamOS 7.2

Esta branch é a linha experimental do Charcoal para o **SteamOS 7.2**. Ela fica isolada da linha estável `master`/6.16.

> **Importante:** os builds produzidos pela `kernel-7.2` são experimentais e são publicados somente como **pré-releases do GitHub**. O instalador estável do Charcoal não instala esses builds.

## Política de fonte

O build localiza o pacote-fonte oficial mais recente `linux-neptune-72` no índice de pacotes do SteamOS, converte essa versão para a tag 7.2 correspondente do `linux-integration` da Valve e então resolve a pilha de patches do Charcoal para essa fonte. O pacote-fonte exato, a tag da Valve, origem dos patches, commits e SHA-256 ficam registrados nos logs do build e no `patch-lock.json`.

## Instalar a pré-release do SteamOS 7.2

Execute no Modo Desktop do SteamOS:

```bash
curl -fsSL https://raw.githubusercontent.com/zarpon/linux-charcoal-vulcano/kernel-7.2/install-charcoal.sh -o install-charcoal-7.2.sh && bash install-charcoal-7.2.sh
```

O instalador fica preso exclusivamente à linha 7.2. Ele procura nas Releases do GitHub a pré-release publicada mais recente cuja tag comece com `charcoal-7.2-` e aceita apenas um pacote `linux-charcoal-72-*.zip` acompanhado do arquivo `RELEASE-ZIP-SHA256SUM`.

Antes de alterar qualquer pacote do sistema, o instalador:

- baixa completamente a pré-release;
- valida o SHA-256 do ZIP da release;
- valida o SHA-256 dos dois pacotes internos, kernel `linux-charcoal-72` e headers;
- faz um preflight dos pacotes validados com o pacman;
- detecta os pacotes instalados cujo nome começa com `linux-charcoal`;
- exibe a transação e exige confirmação antes de tornar o SteamOS gravável.

Somente depois dessas validações e da confirmação, qualquer kernel Charcoal anterior é removido com uma transação restrita `pacman -Rdd`, e em seguida são instalados o kernel e os headers 7.2 previamente verificados. Pacotes como `linux-neptune-*` e quaisquer pacotes não relacionados nunca entram na lista de remoção. O `-Rdd` é usado especificamente para impedir remoção em cascata de dependências.

Se os arquivos exatos dos pacotes Charcoal anteriores ainda existirem em `/var/cache/pacman/pkg`, o instalador os copia para a área temporária antes da remoção e tenta restaurá-los automaticamente caso a instalação dos novos pacotes 7.2 falhe. Se não houver material de rollback disponível e a instalação falhar após a remoção, o instalador interrompe o procedimento, avisa para **não reiniciar** e restaura o sistema de arquivos raiz do SteamOS para modo somente leitura.

O instalador nunca reinicia o aparelho automaticamente. Depois de uma instalação concluída com sucesso, reinicie manualmente e confirme:

```bash
uname -r
```

O resultado deve conter `charcoal-72`.

## Política de releases desta branch

Todo build de kernel concluído com sucesso a partir da `kernel-7.2` é empacotado em ZIP, recebe metadados SHA-256 e é publicado obrigatoriamente como **pré-release** do GitHub usando uma tag `charcoal-7.2-...`. Se a mesma execução do workflow for repetida, os assets da mesma pré-release são atualizados em vez de criar uma release estável.

O instalador 7.2 não usa o endpoint estável `releases/latest`, porque pré-releases não fazem parte dessa seleção estável do GitHub.

## Configuração atual do kernel 7.2

A branch 7.2 mantém as configurações de jogos e memória do Charcoal, incluindo o port específico do zram-ir para 7.2. A política esperada de ZRAM continua sendo LZ4 como compressor primário e ZSTD como recompressor de prioridade 1, com o nível equivalente a `zstd --fast=1` definido no próprio port do kernel.

## Workflow de build

O workflow dedicado é:

`.github/workflows/build-kernel-7.2.yml`

Ele executa apenas para a branch `kernel-7.2` ou por disparo manual nessa branch. Após uma compilação bem-sucedida, o workflow gera o bundle e publica a pré-release. Se a publicação falhar, o workflow também falha, evitando deixar silenciosamente um kernel compilado sem a pré-release correspondente.

## Aviso

O suporte ao SteamOS 7.2 desta branch é experimental. Use este instalador apenas se a intenção for testar essa linha de pré-release e se houver conhecimento de como restaurar o kernel stock do SteamOS em caso de necessidade.

Para a linha estável do Charcoal, utilize a branch `master`.
