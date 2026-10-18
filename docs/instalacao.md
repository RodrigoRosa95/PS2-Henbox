# Instalação — requisitos, memory card e pendrive

O que você precisa ter e onde vai cada arquivo. O resumo: o **memory card só precisa abrir o OPL**; o **pendrive do PS2
só precisa da pasta `APPS/NAVEGADOR`**; todo o resto (Neutrino, loja, servidores) fica na TV box e no servidor em nuvem.

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

O app do celular grava o `navegador.elf` e o `IPCONFIG.DAT` no pendrive com os botões **Gravar navegador.elf no
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
2. No celular, abra o `InstaladorPS2.apk` → **Procurar TV boxes** → toque na sua → aceite **Permitir depuração** na TV
   (marque *Sempre permitir*) → **Instalar / atualizar tudo**.
3. Precisa de uns **400 MB livres** e de internet na 1ª vez (o Termux baixa o Python).
4. Em **IP do PS2**, ponha o mesmo IP do `IPCONFIG.DAT` e toque em **Salvar IP na TV box**.

O instalador põe na box o Termux, o Termux:Boot, o app do navegador (WebView), os servidores e o Neutrino.

Jogos que ficam **na própria TV box** (opcional, abrem mais rápido): um pendrive ou HD na USB da box com as pastas

```
DVD/   ← ISOs de DVD
CD/    ← ISOs de CD
```

## Servidor em nuvem (opcional)

Sem ele, a TV box mostra o menu, os vídeos dela e roda os jogos do pendrive dela. Com ele, entram o catálogo da loja,
os jogos e vídeos da coleção e o acesso fora de casa.

| Serviço | Arquivo | Porta | Pasta da coleção |
| --- | --- | --- | --- |
| Loja e catálogo | `servidor.py` | 8770 | — |
| Vídeos, ROMs, ISOs e loja para a TV box | `navegador/videos_https.py` | 8781 | `PS2/DVD`, `PS2/CD`, `PS2/VIDEOS-PS2` (variáveis `PS2_JOGOS` e `PS2_VIDEOS`) |
| Acesso fora de casa | túnel Cloudflare (`cloudflared`) | → 8781 | — |

Na primeira execução, o `videos_https.py` cria a chave `videos_https.chave`. Ela vai no `config.json` da TV box
(o `gerar-pacote.sh` do instalador já põe).

## Primeiro uso

1. TV box ligada há 1 minuto.
2. PS2: OPL → **Apps** → **Navegador (rede direta)**.
3. A barra azul pulsa enquanto a TV box conecta; em poucos segundos aparece o menu **Loja / Vídeos**.

Se a barra não sair: confira o cabo, se o IP do `IPCONFIG.DAT` é o mesmo salvo na TV box, e o **Ver estado** no app do
celular.
