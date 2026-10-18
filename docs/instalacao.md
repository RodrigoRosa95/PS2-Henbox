# Instalação — requisitos, memory card e pendrive

O que você precisa ter e onde vai cada arquivo. O resumo: o **memory card só precisa abrir o OPL**; o **pendrive do PS2
só precisa da pasta `APPS/NAVEGADOR`**; todo o resto (Neutrino, loja, servidores) fica na TV box e no servidor em nuvem.

## Caminho rápido

1. **Pendrive do PS2:** baixe o [`pendrive.zip`](https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/releases/latest/download/pendrive.zip) e descompacte na raiz de um pendrive FAT32.
2. **Instalador:** instale o [`InstaladorPS2-publico.apk`](https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/releases/latest/download/InstaladorPS2-publico.apk).
3. **TV box**, de um destes jeitos:
   - **Direto na TV box:** instale o mesmo APK na própria box (pendrive + gerenciador de arquivos, ou
     `adb install`). Abra **Instalador PS2** no launcher da TV → **Instalar NESTA TV box** (aceite o pedido de root)
     → **Instalar / atualizar tudo**. Não precisa de celular nem de ADB pela rede.
   - **Pelo celular:** ligue a depuração ADB pela rede na box. No app do celular: **Procurar TV boxes** → toque na
     sua → aceite na TV → **Instalar / atualizar tudo**.

   No fim, o app mostra o IP do PS2; se não for `192.168.4.230`, crie no pendrive o `APPS/NAVEGADOR/IPCONFIG.DAT` com
   a linha que ele mostrar.
4. **Cabo:** PS2 na porta de rede da TV box (ou os dois no mesmo roteador).
5. **PS2:** OPL → **Apps** → **Navegador (rede direta)**.

Opcional — **servidor em nuvem** com a sua coleção: num PC Linux, `servidor/instalar.sh /pasta/da/colecao` e copie o
endereço e a chave que ele mostrar para o app (**Salvar servidor na TV box**).

O resto desta página é o detalhe de cada passo.

## Requisitos

| Peça | O que precisa | Para quê |
| --- | --- | --- |
| PlayStation 2 | Fat com adaptador de rede (SCPH-10350) ou Slim (rede embutida) | rodar o navegador e os jogos |
| Jeito de abrir homebrew | FreeMcBoot / OpenTuna no memory card (ou modchip) | abrir o OPL |
| OPL | Open PS2 Loader 1.1.0 ou mais novo | abrir o navegador pela aba **Apps** |
| Pendrive no PS2 | FAT32, na USB da frente | guardar o `navegador.elf` (e as ROMs de SNES que a loja gravar) |
| Cabo de rede | PS2 → porta de rede da TV box, ou PS2 e TV box no mesmo roteador | o PS2 recebe a tela e os jogos pela rede |
| TV box Android | com **root**, porta de rede, ADB pela rede ligado | desenha as páginas e serve os jogos |
| Celular Android | qualquer um, na mesma rede da TV box | instalar tudo com o `InstaladorPS2.apk` |
| Servidor em nuvem | PC/notebook com Linux e a coleção (opcional) | catálogo da loja, jogos e vídeos que não estão na TV box, acesso fora de casa |
| Controle | DualShock 2; DualShock 4 por Bluetooth também funciona (adaptador USB) | navegar |

Use só cópias dos seus próprios jogos.

## Memory card

Nada deste projeto vai no memory card. Ele só precisa:

1. **Abrir o OPL** — por exemplo, FreeMcBoot com o OPL no menu (`mc0:/BOOT/` ou `mc0:/APPS/`), ou o OPL aberto pelo
   wLaunchELF.
2. **Guardar as configurações do OPL** (`mc0:/OPL/`), que o próprio OPL cria.

No OPL, em **Configurações**, deixe o **modo de início do dispositivo USB** em *Automático*, para a aba **Apps** listar
os apps do pendrive. Não é preciso configurar rede no OPL para o navegador: ele liga a rede sozinho.

## Pendrive do PS2

Formate em **FAT32** e crie esta estrutura:

```
APPS/
  NAVEGADOR/
    navegador.elf      ← o programa (gerado em navegador/ps2/, ou copiado da TV box pelo app do celular)
    title.cfg          ← faz o navegador aparecer na aba Apps do OPL
    IPCONFIG.DAT       ← opcional: IP do PS2, se não for 192.168.4.230
```

`title.cfg` (texto simples):

```
title=Navegador (rede direta)
boot=navegador.elf
```

`IPCONFIG.DAT` (uma linha: IP, máscara e gateway do PS2, separados por espaço):

```
192.168.4.230 255.255.255.0 192.168.4.1
```

Sem o `IPCONFIG.DAT`, o PS2 usa `192.168.4.230 / 255.255.255.0 / 192.168.4.1`. Escolha um IP livre na rede da TV box.
O PS2 não pega IP por DHCP.

O [`pendrive.zip`](https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/releases/latest/download/pendrive.zip) já traz a pasta `APPS/NAVEGADOR` pronta. O app do celular também grava o `navegador.elf` e o `IPCONFIG.DAT` no pendrive com os botões **Gravar navegador.elf no
pendrive do PS2** e **Gravar IP no pendrive do PS2** (com o navegador já aberto no PS2). Na primeira vez, copie pelo PC.

A loja cria sozinha, quando você usa o Super Nintendo:

```
SNES/                 ← ROMs gravadas pela loja
APPS/RETROARCH/       ← emulador de SNES, gravado junto com a 1ª ROM
```

**Não precisa** pôr Neutrino, ISOs nem módulos no pendrive: os jogos pela rede são lidos da TV box.

## TV box

1. Ligue o modo desenvolvedor e a **depuração ADB pela rede** (porta 5555). O app do celular mostra o passo a passo se
   não achar a box.
2. No celular, abra o `InstaladorPS2-publico.apk` → **Procurar TV boxes** → toque na sua → aceite **Permitir depuração** na TV
   (marque *Sempre permitir*) → **Instalar / atualizar tudo**.
3. Precisa de uns **400 MB livres** e de internet na 1ª vez (o Termux baixa o Python).
4. **IP do PS2 automático:** se o IP padrão não for da rede do cabo da box, o instalador escolhe um livre nela e mostra
   a linha do `IPCONFIG.DAT`. Para trocar à mão: **IP do PS2** → **Salvar IP na TV box**.
5. **Servidor em nuvem (opcional):** endereço e chave → **Salvar servidor na TV box**.

O instalador põe na box o Termux, o Termux:Boot, o app do navegador (WebView), os servidores e o
[Neutrino](https://github.com/rickgaiser/neutrino) 1.8.0 oficial (licença AFL-3.0, sem modificações).

Jogos que ficam **na própria TV box** (opcional, abrem mais rápido): um pendrive ou HD na USB da box com as pastas

```
DVD/   ← ISOs de DVD
CD/    ← ISOs de CD
```

## Servidor em nuvem (opcional)

Sem ele, a TV box mostra o menu, os vídeos dela e roda os jogos do pendrive dela. Com ele, entram o catálogo da loja,
os jogos e vídeos da coleção e o acesso fora de casa.

Num PC Linux com Python 3, na pasta do repositório:

```
servidor/instalar.sh /pasta/da/colecao [IP_DA_TV_BOX]
```

Ele cria `DVD/`, `CD/` e `VIDEOS-PS2/` na coleção, liga os serviços (PM2, ou systemd do usuário) e mostra o
**endereço** e a **chave** para pôr no app do celular. Os ISOs vão em `DVD/` e `CD/`.

| Serviço | Arquivo | Porta | Pasta da coleção |
| --- | --- | --- | --- |
| Loja e catálogo | `servidor.py` | 8770 | — |
| Vídeos, ROMs, ISOs e loja para a TV box | `navegador/videos_https.py` | 8781 | `PS2/DVD`, `PS2/CD`, `PS2/VIDEOS-PS2` (variáveis `PS2_JOGOS` e `PS2_VIDEOS`) |
| Acesso fora de casa | túnel Cloudflare (`cloudflared`) | → 8781 | — |

**Fora de casa:** crie um túnel HTTPS (ex.: Cloudflare Tunnel) para a porta 8781 e use o endereço `https://…` no app.
A chave fica em `navegador/videos_https.chave`.

## Primeiro uso

1. TV box ligada há 1 minuto.
2. PS2: OPL → **Apps** → **Navegador (rede direta)**.
3. A barra azul pulsa enquanto a TV box conecta; em poucos segundos aparece o menu **Loja / Vídeos**.

Se a barra não sair: confira o cabo, se o IP do `IPCONFIG.DAT` é o mesmo salvo na TV box, e o **Ver estado** no app do
celular.
