# ps2GamesCLoudinOPl — PS2 Navegador

O projeto ps2GamesCLoudinOPl é uma solução criativa que transforma o seu PlayStation 2 em um console capaz de acessar uma loja de jogos online e até mesmo executar jogos diretamente da nuvem, sem a necessidade de baixá-los completamente para um pendrive ou HD.

🎮 Entendendo o Projeto: A Arquitetura da Nuvem no PS2
A magia acontece através da cooperação entre três dispositivos principais, cada um com uma função bem definida:

PlayStation 2 (Cliente Magro): O PS2 não faz o trabalho pesado. Ele apenas exibe a imagem que recebe e envia os comandos do controle de volta. Ele se conecta à TV box através de rede.

TV Box Android (O Cérebro): Este é o coração do sistema. A TV box é responsável por renderizar a interface da loja (que você vê no PS2), gerenciar os arquivos e servir os jogos. Ela "desenha" a página e envia a imagem pronta para o PS2, como se fosse uma conexão remota.



![Arquitetura](docs/arquitetura.png)

**Veja o link demonstratibo de loja:** [(apenas visualização)](https://ps2videos.rodrigoflix.com/loja/?convite=DUxWDdci7OSb). São
os jogos da coleção pessoal do autor; nada é baixado nesse link demonstrativo. Jogar e baixar funcionam apenas no PS2.

## Telas (como aparecem no PS2, 640x448)

| Menu | Loja |
| --- | --- |
| ![Menu inicial](docs/telas/1-menu.png) | ![Loja](docs/telas/2-loja.png) |
| **Jogo pela rede** | **Vídeos** |
| ![Jogar pela rede](docs/telas/3-jogar-pela-rede.png) | ![Vídeos](docs/telas/4-videos.png) |

No painel do jogo, **☁ Jogar pela rede** abre o Neutrino no PS2 lendo a ISO direto do servidor em nuvem da coleção, aos pedaços,
atraves da TV box em HTTPS.

## Baixar

Arquivos prontos (pasta [`downloads/`](downloads/), também na [Release](https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/releases/latest)):
[`pendrive.zip`](https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/raw/main/downloads/pendrive.zip) (pasta `APPS/NAVEGADOR` para o pendrive do PS2) e
[`InstaladorPS2-publico.apk`](https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/raw/main/downloads/InstaladorPS2-publico.apk) (no celular ou na própria TV box: instala tudo na
TV box, com o [Neutrino](https://github.com/rickgaiser/neutrino) 1.8.0 oficial, AFL-3.0). Passo a passo em
[Instalação](docs/instalacao.md).

## Documentação

- [Instalação](docs/instalacao.md) — requisitos e o que vai no memory card, no pendrive do PS2, na TV box e no servidor
- [Fluxo técnico do sistema](docs/fluxo-tecnico.md) — peças, portas, protocolos, fluxos e problemas resolvidos
- [Guia para novo usuário](docs/guia-novo-usuario.md) — uso, controles, problemas comuns e roteiro de apresentação

## Estrutura

| Pasta | O que é |
| --- | --- |
| `navegador/ps2/` | `navegador.elf` (ps2sdk + gsKit): tela, controle, vídeo MPEG-2 no IPU, cópias para o pendrive, abertura do Neutrino |
| `navegador/navlink/` | `navlink.irx`: o servidor de arquivos `host:` do PS2Link na porta TCP 0x4721 (código do ps2link, ver `LICENSE-PS2Link`) |
| `navegador/*.py` | servidores da TV box (`navegador_servidor`, `servidor_host`, `videos`, `udpfs_nuvem`, `configurar`) e do notebook (`videos_https`) |
| `navegador/tvbox/` | scripts de inicialização na TV box (Termux / Termux:Boot) |
| `navegador/tvbox-app/` | app Android da TV box: WebView numa tela virtual 640x448 + ponte DevTools |
| `navegador/instalador/` | app Android do celular: acha a TV box por ADB, instala tudo e mostra o estado |
| `lancador/` | `abrir.elf`: abre um ELF do memory card a partir do PS2Link |
| raiz | loja e cinema do notebook (`servidor.py`, `loja.html`, `cinema.py`…) |

## Compilar

- PS2 (ps2sdk + gsKit em `/usr/local/ps2dev`): `make -C navegador/navlink && make -C navegador/ps2`
- App da TV box: `navegador/tvbox-app/montar.sh` (aapt, dx, android-23, apksigner — sem Gradle)
- Instalador do celular: `navegador/instalador/terceiros/baixar.sh` e `navegador/instalador/montar.sh`
  (`PUBLICO=1 navegador/instalador/montar.sh` gera o `InstaladorPS2-publico.apk`, sem chave nem endereços)
- Servidor em nuvem: `servidor/instalar.sh /pasta/da/colecao`

O pacote do instalador também precisa, fora deste repositório: `neutrino/` e `udpfs_server/` (release oficial do
[Neutrino](https://github.com/rickgaiser/neutrino)), o SNESticle e o SMS em `navegador/ps2/`, e a chave
`navegador/videos_https.chave` (criada pelo `videos_https.py` na primeira execução).

## Avisos

- Use só cópias dos seus próprios jogos. Nenhum jogo ou ROM está neste repositório; as capas nas telas são só ilustração.
- O acesso de fora de casa passa por um túnel Cloudflare protegido por chave; os termos do Cloudflare restringem
  servir vídeo pelo túnel gratuito.
- A TV box precisa de root; o instalador usa o ADB pela rede.
