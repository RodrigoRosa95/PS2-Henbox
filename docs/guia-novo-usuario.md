# PS2 Navegador — Guia de apresentação para novo usuário

Oct 18, 2026 · @Rodrigo Rosa

## O que é

O PS2 Navegador transforma o PlayStation 2 numa central de mídia: pelo controle você escolhe jogos e vídeos numa loja na tela, e a TV box ao lado faz todo o trabalho pesado.

O PS2 acessa o navegador da TV box (o Chrome do Android, pelo WebView) como se fosse um VNC. A box desenha a página e manda a imagem pronta para o PS2. O PS2 só mostra a tela e devolve os botões do controle.

A loja de jogos é parecida com a loja da HEN do PS3: você navega pelas capas e escolhe o jogo. A diferença é que dá para fazer duas coisas direto do PS2: baixar o jogo da loja para o pendrive, ou rodar o jogo em nuvem, sem copiar nada.

O que dá para fazer hoje:

- **Jogar PS2 pela rede**, direto do servidor em nuvem da coleção, sem copiar o jogo para o pendrive ("☁ Jogar pela rede").
- **Jogar Super Nintendo**: a loja grava a ROM e o emulador no pendrive do PS2 e abre o jogo.
- **Assistir vídeos** já preparados para o PS2, da TV box ou da coleção.
- **Funciona fora de casa**: a TV box busca tudo pela internet, com acesso protegido por chave.

## O que precisa ter

| Item | Detalhe |
| --- | --- |
| PS2 com adaptador de rede | cabo de rede ligado ao roteador ou direto na TV box |
| Pendrive no PS2 (FAT32) | com `APPS/NAVEGADOR/navegador.elf`, `title.cfg` e, se o IP for diferente, `IPCONFIG.DAT` |
| OPL no PS2 | é por ele que o navegador abre (Apps) |
| TV box já instalada | com o app PS2 Navegador e os servidores (o app instalador do celular faz isso) |
| Controle | com fio na porta 1 ou DualShock 4 por Bluetooth; mouse e teclado USB também funcionam |
| Internet na TV box | para buscar jogos, ROMs e vídeos da coleção quando ela está fora de casa |

## Primeiro uso

1. Ligue a TV box e espere uns 30 segundos (os servidores sobem sozinhos).
2. Ligue o PS2 e abra o **OPL**.
3. Vá em **Apps → Navegador (rede direta)**.
4. Aparece uma barra azul pulsando enquanto o PS2 liga a rede e a TV box se conecta: alguns segundos.
5. Surge o menu com **🛒 Loja** e **🎬 Vídeos**.

| No controle | Faz |
| --- | --- |
| Analógico esquerdo ou direcional | move o cursor |
| X | clica |
| O | volta / para o vídeo |
| Analógico direito | rola a página |
| □ | abre o teclado na tela |
| SELECT + START | sai do navegador |

No vídeo: X ou START pausa, O para e volta ao menu.

## Usando

**Jogos de PS2**

1. **🛒 Loja**, escolha o jogo e aperte X para abrir os detalhes.
2. **▶ Jogar** (jogo já no pendrive da TV box) ou **☁ Jogar pela rede** (jogo só na coleção).
3. A tela fica parada alguns segundos enquanto o PS2 se prepara. Na primeira vez pode demorar mais.
4. O jogo abre. Pela rede, alguns carregamentos ficam um pouco mais lentos que do disco.
5. Para voltar, reinicie o PS2.

**Super Nintendo**

1. **🛒 Loja → Super Nintendo**, escolha a ROM.
2. **Instalar** grava a ROM (e o emulador, na 1ª vez) no pendrive do PS2; acompanhe o andamento na tela.
3. **Jogar** fecha o navegador e abre o jogo no SNESticle.

**Vídeos**

1. **🎬 Vídeos** mostra os da TV box ("na TV box") e os da coleção ("do servidor em nuvem").
2. Escolha e aperte X. No início aparece uma barra azul enquanto o vídeo carrega.

## Problemas comuns

| O que aparece | O que fazer |
| --- | --- |
| Barra azul pulsando sem parar | confira se a TV box está ligada e na mesma rede (ou com o cabo direto no PS2); espere 30 s; se continuar, reinicie a TV box |
| Tela travada depois de reiniciar o PS2 | espere até 20 s: a TV box percebe a queda e reconecta sozinha |
| "Jogar pela rede" volta ao menu do console | reinicie o PS2 e abra o navegador de novo; se repetir, avise com o nome do jogo |
| Jogo pela rede lento em alguns carregamentos | normal pela internet; em casa fica mais rápido |
| ROM não grava ("pendrive não encontrado") | confira se o pendrive está espetado no PS2 e tem espaço |
| O IP do PS2 mudou ou a rede é outra | no app do celular, troque o IP e use "Gravar IP no pendrive" com o navegador aberto |
| Nada responde | reinicie a TV box (os servidores sobem sozinhos) e depois o PS2 |

## Roteiro de apresentação (5 minutos)

1. **Minuto 0–1: abertura.** Mostre o PS2 ligado ao lado da TV box e diga a ideia: o PS2 vira uma central de jogos e vídeos, com a TV box fazendo o trabalho pesado.
2. **Minuto 1–2: entrada.** OPL → Apps → Navegador. Mostre a barra azul virando o menu em poucos segundos.
3. **Minuto 2–3: loja.** Navegue pelas capas com o analógico, abra um jogo e mostre os detalhes (tamanho, região, onde está).
4. **Minuto 3–4: jogo pela rede.** Escolha um jogo que não está na TV box e aperte ☁ Jogar pela rede. Explique que ele vem do servidor em nuvem da coleção enquanto carrega.
5. **Minuto 4–5: fechamento.** Reinicie o PS2, abra Vídeos e toque um trecho. Termine com: tudo isso funciona também fora de casa, pela internet.

Prepare antes: a TV box ligada há 1 minuto, o navegador.elf no pendrive e um jogo escolhido que já tenha aberto pela rede.
