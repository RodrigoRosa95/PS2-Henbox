# Central do celular, conquistas acumuladas e música da loja (24/10/2026)

Novidades do PS2 Henbox de 24/10/2026. O que ainda não foi testado no PS2 ou num celular de verdade está marcado.
O código está publicado; o pacote de atualização automática (`downloads/`) **ainda não** leva essas mudanças.

## 📱 Central do celular

No app **PS2 Henbox** (versão 2.2), o botão **🎮 Central…** abre a página `/celular` do `central.py`, que roda na TV box na porta 8785.
Com Android 4.4 (WebView antigo) a box serve `central-compat.html`, gerada pelo `central_compat.js` (Babel → ES5).

| Aba | O que faz |
| --- | --- |
| **Jogos** | ISOs do pendrive da box com capa. **🖼 Baixar capas** lê o código do jogo no `SYSTEM.CNF` e baixa a capa do [xlenore/ps2-covers](https://github.com/xlenore/ps2-covers) para `ART/<código>_COV.jpg`, como o OPL Manager faz no PC. |
| **Arquivos** | Explorador do pendrive da box e, com o navegador aberto no PS2, do `mc0:`, `mc1:` e `mass:` (ops 5 listar, 6 criar pasta e 7 apagar pasta do `navegador.elf`). Baixar, enviar, renomear e apagar. Pastas do sistema, do exploit, do OPL e do navegador ficam protegidas. |
| **Controle** | Touchpad, teclado, rolagem e botões do controle pelo celular. Funciona também na Loja. O PS2 lê o cursor em `host:cursor.bin` (bit `0x400` do cmd). ⚠ Cursor no PS2 real não testado. |
| **Online** | Kits da comunidade (ver abaixo). |

**ISOs do celular:** o `ServidorIsos.java` procura ISOs na memória do celular e serve por HTTP (porta 8786, com chave e Range).
Dá para **jogar direto do celular** (o `udpfs_nuvem.py` procura no celular antes do notebook) ou **mandar para o pendrive da box** (com retomada).
⚠ Testado instalando o app na própria box; num celular de verdade, não.

## 🌐 Kits para jogar online

`kits_servidor.py` (porta 8792) guarda kits da comunidade: **VMC, CFG do OPL, patch PPF, capa e DNS**. **Nunca o ISO**: arquivos com assinatura de ISO (`CD001`) são recusados. Cada um usa o próprio jogo.

- Quem envia escolhe o ISO da própria box, e o kit leva o hash do jogo (`ra_hash`) para conferir a versão.
- Kit novo fica em `pendentes/` até ser aprovado (`kits_servidor.py pendentes | aprovar | recusar | testado`).
- **Aplicar** na box:
  - guarda o VMC antigo;
  - mescla o CFG;
  - aplica o PPF com **desfazer**;
  - grava a capa;
  - liga o DNS do kit por 6 h (`dns-kit.json`).

## 🏆 Conquistas acumuladas com voz

As conquistas desbloqueadas durante o jogo ficam guardadas. Quando o `navegador.elf` abre de novo, o PS2 mostra:

1. um "plim" e a voz (Piper pt-BR), por exemplo *"Você desbloqueou 7 conquistas no jogo Black."* ou *"…9 conquistas: 7 no Black e 2 no Burnout 3."*;
2. cada conquista com medalha, descrição, pontos e jogo (○ pula);
3. um resumo com o total de conquistas e pontos.

A frase é gerada pela rota `POST /voz` do `videos_https.py`. Sem o servidor, a box usa as frases prontas `sons/conquistas-N.raw`.

## 🎵 Música de fundo da loja (só as suas)

O pacote **não traz nenhuma música**. Quem quiser coloca **mp3, ogg, wav, flac, m4a ou opus** na pasta **`MUSICAS`** do pendrive da TV box.
O `videos.py` converte as músicas com o ffmpeg para o som do PS2 (22050 Hz mono, até 90 s, com entrada e saída suaves) em `ps2/trilhas-usuario/`.
Na Loja aparece a barra **◀ faixa ▶ 🔈**. Com a pasta vazia, a barra some.

- A música só toca na Loja. O número da faixa vai nos bits 24-31 do cmd; quando ele muda, o PS2 relê `host:musica.raw`.
- O som sai em blocos de 1024 amostras. O anel do audsrv só tem ~50 ms (4.700 bytes a 22050 Hz mono), e com 2048 ele calava.
- No Termux, o ffmpeg precisou de `apt-get install --only-upgrade libc++`.
- `sons/gerar_trilhas.py` sintetiza faixas 8-bit originais, para quem quiser criar as próprias. Elas não vão no pacote.

## 💾 Jogos do pendrive do PS2 lidos ao abrir

Uns 15 s depois de o navegador abrir, a box lista `mass:/DVD` e `mass:/CD` do pendrive no USB do PS2 e atualiza as abas **💾 No pendrive do PS2** e **🌐 Jogar online**:

- entram os jogos colocados pelo PC ou pelo OPL Manager;
- saem os que foram apagados;
- os jogos da pasta `CD` abrem como CD.

Também há o botão **🔄 Ler o pendrive de novo**.

> Problema resolvido: no PS2 real, o `readdir` do newlib devolvia **nomes vazios** no pendrive. O driver BDM (iomanX) responde no formato `iox_dirent_t`, com o nome no byte 64, e o fio do ioman lê `io_dirent_t`, com o nome no byte 40. A op 5 agora usa `fioDread` direto e aceita os dois formatos.

## 🔄 Reiniciar sistema

Botão na tela inicial, com confirmação. O navegador fecha, o PS2 volta ao PS2Link do memory card e o `servidor_host.py` da box abre o navegador de novo sozinho, com o IOP e a rede do zero.

## Outras correções

- **"Servidor em nuvem fora do alcance" na Loja:** com o PS2 no cabo, o Android passava a usar a rede do cabo (sem rota) como padrão. O `henbox-root.sh` agora devolve a rede padrão ao Wi-Fi (`ndc network default set <netId>`).
- A tela inicial não tem mais o botão 🎬 Vídeos.
