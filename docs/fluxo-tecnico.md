# PS2 Navegador — Fluxo técnico do sistema

Oct 18, 2026 · @Rodrigo Rosa

## Visão geral

O sistema tem três aparelhos com papéis fixos: o **PS2** só mostra a imagem e devolve o controle, a **TV box** desenha as páginas e executa todas as ações, e o **notebook** guarda a coleção e a entrega com chave, pela rede local ou pelo Cloudflare. O celular entra só para instalar e acompanhar a box.

![Arquitetura: PS2, TV box, notebook, Cloudflare e celular](arquitetura.png)

A box conecta no PS2 de duas formas: TCP na porta 0x4721 (arquivos `host:` da tela, controle, cópias e Neutrino) e UDP 62966 (leitura dos jogos pelo Neutrino). Para o notebook, tenta primeiro a rede local (8781) e depois o HTTPS.

## PS2: navegador.elf + navlink.irx

O PS2 é um cliente magro: mostra a imagem que chega, desenha o cursor e devolve controle, mouse e teclado. Toda a conversa com a TV box passa por **arquivos** no dispositivo `host:` (o protocolo de arquivos do PS2Link).

**Modos de abertura**

| Aberto por | Rede usada | Como o `host:` existe |
| --- | --- | --- |
| OPL (pendrive, `mass:/APPS/NAVEGADOR/navegador.elf`) | própria: o navegador reinicia o IOP e carrega `poweroff`, `ps2dev9`, `netman`, `smap`, `ps2ip-nm`, `udptty`, `ioptrap` e `navlink.irx` (mesma ordem do PS2Link) | o `navlink.irx` escuta na porta TCP **0x4721** e a box conecta nele |
| PS2Link (`ps2client execee host:navegador.elf`) | a do PS2Link | o próprio PS2Link; com o argumento `rede`, força o modo OPL |

**IP do PS2:** lido de `IPCONFIG.DAT` ao lado do ELF no pendrive (`IP MÁSCARA GATEWAY`, formato do PS2Link). Sem o arquivo, usa 192.168.4.230 / 255.255.255.0 / 192.168.4.1. A leitura é feita uma vez: IOP só com o driver do pendrive, depois reinicia para a rede.

**Arquivos trocados pelo `host:`** (todos em `~/ps2nav/ps2` na box):

- `dif.bin` / `completa.bin`: mudanças da tela (retângulos RGBX comprimidos com zlib) e comandos (bit 0x100 música, 0x200 há pedido).
- `entrada.bin`: escrito pelo PS2 várias vezes por segundo (botões, cursor, analógicos, teclas, estado do pedido e do vídeo).
- `pedido.bin`: uma operação por vez — 0 copiar para o pendrive, 1 executar um ELF, 2 tocar vídeo, 3 apagar.

**Executar um ELF (op 1):** do pendrive (SNESticle) usa o elf-loader do ps2sdk. Do `host:` (Neutrino) faz como o `execee` do PS2Link: IOP limpo só com a rede, `SifLoadElf` pelo `host:`, thread nova com pilha e argumentos no alto da memória (0x1F00000) e o gsKit desligado, porque o Neutrino se descompacta em 0x100000, por cima do navegador.

**Vídeo:** MPEG-2 640x400 decodificado no IPU com a libmpeg. Os dados vão ao IPU escrevendo direto nos registradores do canal 4, como o SMS, com pré-carga de 1 MB e pausa abaixo de 256 KB; o relógio é o áudio (PCM 22050 Hz estéreo pelo audsrv).

## TV box: o cérebro local

A TV box (Android com root, 192.168.4.121) faz o que antes era do notebook: desenha as páginas, serve os arquivos do PS2 e executa as ações. Tudo roda no Termux, ligado sozinho pelo Termux:Boot.

| Peça | O que faz | Porta |
| --- | --- | --- |
| App **PS2 Navegador** (`br.ps2nav`) | WebView numa tela virtual invisível de 640x448; ponte para o DevTools do WebView e saída crua dos quadros | 9222 (DevTools), 9223 (quadros RGBA) |
| `navegador_servidor.py` | comanda o WebView pelo DevTools, recorta as mudanças da tela, grava `dif.bin`, lê `entrada.bin` e transforma em clique/tecla; fila de pedidos | 8772 (controle: `status`, `loja`, `copiar2`, `jogar`, `neutrino`, `video`, `sair`) |
| `servidor_host.py` | servidor de arquivos `host:` (protocolo do ps2client); conecta no PS2 e, se o IP não responder, procura o PS2 nas redes locais | cliente da 0x4721 do PS2 |
| `videos.py` | página inicial (Loja e Vídeos); proxy da loja do notebook com a chave; ações de SNES e de jogo de PS2 executadas aqui | 8780 |
| `udpfs_nuvem.py` | servidor oficial do Neutrino (`udpfs_server.py`) servindo o pendrive da box; ISO ausente vem do notebook em blocos de 1 MB (cache de 48, 3 à frente) | UDP 62966 |
| `configurar.py` | `config.json` único: IP do PS2, endereços do notebook, chave; gera `remoto.json`, `IPCONFIG.DAT` e o `ip=` do Neutrino; `estado` em JSON para o app do celular | — |

**Por que WebView e não Chrome:** o Chromium do Termux só existe em 64 bits e a box roda 32 bits. O WebView 74 da box não entrega quadros ao `captureScreenshot` nem amplia pela emulação: a imagem sai do `ImageReader` da tela virtual e o zoom 1,5 das páginas do sistema é feito por CSS.

**Rodar coisas no Termux:** só pelo `RUN_COMMAND` (`allow-external-apps=true`). O `su` desta box não passa o grupo de internet para outro usuário e o `apt` do Termux recusa rodar como root.

**Scripts** (`~/ps2nav`): `iniciar.sh` (tudo), `so-host.sh`, `so-navegador.sh`, `so-videos.sh`; `~/.termux/boot/ps2nav` e `~/.termux/boot/udpfs-ps2.sh` na inicialização.

## Notebook: a coleção e o acesso de fora

O notebook guarda o conteúdo (jogos, ROMs, vídeos, catálogo) e o entrega só para leitura, sempre com a chave. As ações sobre aparelhos ficam na TV box.

| Serviço (PM2) | O que entrega | Endereço |
| --- | --- | --- |
| `ps2-videos` (`videos_https.py`) | `/loja/<lista fixa>` (página, catálogo, capas — só GET), `/rom/<arquivo>` (ROM de SNES), `/iso/DVD/<arquivo>` (ISO de PS2, com Range) | :8781 na rede local; `https://ps2videos.rodrigoflix.com` pelo túnel Cloudflare |
| `ps2-web` (`servidor.py`) | a loja original (`loja.html`, catálogo, instalação de ISO no pendrive da box de casa por ADB) | :8770 (só na rede local) |
| Jellyfin | filmes e séries (o Cinema converte para o PS2 com ffmpeg, só no notebook) | :8096 |

**Chave:** `navegador/videos_https.chave` (cabeçalho `X-Chave`); sem ela, 403. A TV box guarda a mesma em `~/ps2nav/config.json` / `remoto.json`.

**Cloudflare:** a regra `ps2videos.rodrigoflix.com → http://localhost:8781` foi acrescentada ao `/etc/cloudflared/config.yml` (backup em `config.yml.bak-antes-ps2videos`), antes da regra final 404. As outras regras (Jellyfin, Alexa) não mudaram.

**Ordem de tentativa na box:** primeiro a rede local (`192.168.4.135:8781`, desiste em 3 s), depois o HTTPS; o último endereço que funcionou vai primeiro na próxima vez. Medido na box: 5,4 MB/s pela rede local e 2,6 MB/s pelo Cloudflare.

## Fluxos passo a passo

**Abrir o navegador (OPL)**

1. OPL → Apps → "Navegador (rede direta)" abre `mass:/APPS/NAVEGADOR/navegador.elf`.
2. O navegador lê `IPCONFIG.DAT`, reinicia o IOP com a pilha de rede e o `navlink.irx`, e mostra a barra azul pulsando.
3. O `servidor_host.py` da box conecta na porta 0x4721 do PS2 (se o IP não responder, procura nas redes locais).
4. O PS2 consegue abrir `host:clique.raw`, liga som, controle e a thread de rede; a box já tem a página inicial pronta e manda a tela inteira.

**Tela e controle (ciclo contínuo)**

1. O WebView desenha a página na tela virtual; `navegador_servidor.py` pega o quadro (porta 9223) e compara com o anterior.
2. As regiões que mudaram vão comprimidas para `dif.bin`; o PS2 lê e redesenha.
3. O PS2 grava `entrada.bin`; o servidor converte em movimento do mouse, clique e teclas pelo DevTools.

**Loja → ROM de SNES**

1. A loja (proxy da `videos.py`) mostra o catálogo do notebook.
2. "Instalar": se a ROM não está na box, ela baixa de `/rom/...`; depois pede `copiar` ao navegador.
3. O PS2 copia `host:snes/<rom>` para `mass:/SNES/` (e o SNESticle na 1ª vez).
4. "Jogar": op 1 abre o SNESticle do pendrive com a ROM como argumento.

**Vídeos**

1. "Vídeos" lista os da box (`ps2/video`) e os do notebook (`/lista`).
2. Tocar = `video <id>` (ou `video remoto/<id>`); o PS2 lê `host:video/<id>.m2v` e `.pcm`, que o `servidor_host.py` busca no notebook quando são remotos.

**Jogo de PS2 em nuvem**

1. Na loja, "☁ Jogar pela rede" → `videos.py` acha o ISO no catálogo e manda `neutrino <iso>`.
2. O navegador limpa o IOP (só rede + `navlink`), espera a box reconectar e carrega `host:neutrino/neutrino.elf` com `SifLoadElf`.
3. O Neutrino lê `config/` e `modules/` pelo `host:` da box e monta o ambiente do jogo com `-bsd=udpfs -dvd=udpfs:DVD/<iso>`.
4. O Neutrino acha o servidor de jogos da box por broadcast (UDP 62966) e abre o ISO.
5. O `udpfs_nuvem.py` entrega do pendrive da box ou, se não tiver, busca blocos de 1 MB em `/iso/DVD/<iso>` no notebook enquanto o jogo roda.

**Cópia para o pendrive do PS2 (qualquer arquivo)**

1. Comando `copiar2 host:<origem>|mass:/<destino>|<rótulo>` na porta 8772 da box.
2. O servidor grava `pedido.bin` e liga o bit 0x200 no `dif.bin`.
3. Uma thread do PS2 copia em blocos de 32 KB e informa o andamento no `entrada.bin`; a tela continua respondendo.

## Portas, logs e problemas resolvidos

| Porta | Onde | Para quê |
| --- | --- | --- |
| TCP 0x4721 (18209) | PS2 (`navlink.irx`) | `host:` do navegador; a box conecta |
| UDP 18194 | broadcast do PS2 (`udptty`) | mensagens do PS2 (escutar para depurar) |
| UDP 62966 | TV box | servidor de jogos do Neutrino |
| TCP 8772 | TV box | controle do navegador |
| TCP 8780 | TV box | página inicial, loja e vídeos |
| TCP 9222 / 9223 | TV box (só 127.0.0.1) | DevTools e quadros do WebView |
| TCP 8781 | notebook | conteúdo com chave (também pelo Cloudflare) |
| TCP 5555 | TV box | ADB (app instalador do celular) |

**Logs na box:** `~/ps2nav/host.log` (conexões e arquivos abertos pelo PS2), `navegador.log` (pedidos e estados), `videos.log`, `~/udpfs.log` (descoberta, OPEN e leituras do Neutrino).

| Sintoma | Causa | Solução aplicada |
| --- | --- | --- |
| Vídeo parado no 1º quadro, áudio tocando | callback da libmpeg com chamadas de sistema dentro da interrupção | DMA direto nos registradores do canal 4 + pré-carga |
| Barra azul pulsando para sempre (OPL) | `navlink.irx` importava `ioptrap`/`poweroff` sem eles carregados | imports só de módulos disponíveis; depois a pilha completa do PS2Link |
| Painel da loja fora da tela, capas finas, sem fundo | WebView 74 sem `inset`, `aspect-ratio` e cores `#RRGGBBAA` | equivalentes antigos (`top/left`, alturas fixas, `rgba()`) |
| Neutrino volta ao menu do console | elf-loader reinicia o IOP; IOP cheio; Neutrino se descompacta por cima do navegador | `SifLoadElf` + thread como o PS2Link; IOP limpo; pilha no alto; gsKit desligado |
| `compat.toml` com `fd = -1` | `getstat` do `servidor_host.py` anunciava tamanho errado e desalinhava a conexão | `len` do cabeçalho conta os dados |
| Box presa na conexão antiga após reiniciar o PS2 | socket meio aberto | larga a conexão após 20 s sem pedidos |
