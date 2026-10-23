# OPL-RA do PS2 Henbox

Versão do **OPL-RA** (o Open PS2 Loader com RetroAchievements do
[xeRAbora](https://github.com/hacan359/xerabora), de hacan359) com três mudanças para o navegador do PS2 Henbox.
O ELF pronto está em [`downloads/OPL-RA-Henbox.ELF`](../../downloads/OPL-RA-Henbox.ELF).

| Patch | O que faz |
| --- | --- |
| `0001` | **Abertura direta por SMB**: `OPL-RA.ELF <arquivo.iso> <código> DVD smb` abre o jogo do compartilhamento de `conf_network.cfg` sem passar pelo menu (o OPL oficial só tem `bdm` e `mini`/HDD). |
| `0002` | **Lista de conquistas no memory card**: quando o compartilhamento é só leitura (o Samba de uma TV box Android não grava no pendrive USB dela), o "RA: check game support" guarda `RA/<código>.wl` em `mc0:OPL/RA/` e a abertura procura lá também. |
| `0003` | Na abertura direta por SMB, desmonta o menu com `miniDeinit` (como as aberturas oficiais por BDM e HDD); `deinit` travava com tela preta. |

Compilado com `PADEMU=1`, para o DualShock 3/4 por Bluetooth funcionar dentro do jogo (o build oficial do
xeRAbora usa `PADEMU=0`).

> **Limite atual do xeRAbora:** jogo carregado **pela rede (SMB)** com as conquistas ligadas trava com tela preta,
> porque o jogo e a telemetria disputam o adaptador de rede (o autor confirma na
> [issue #9](https://github.com/hacan359/xerabora/issues/9)). Por isso o navegador abre os jogos com conquistas
> **do pendrive do próprio PS2** (`bdm`). O modo `smb` fica pronto para quando o xeRAbora suportar.

## Compilar

Com o ps2sdk + gsKit em `/usr/local/ps2dev`:

```sh
git clone -b ra https://github.com/hacan359/Open-PS2-Loader.git opl
cd opl && git checkout a9f973974a5fd61707d069961ec0031be19399f7
git am ../0001-*.patch ../0002-*.patch ../0003-*.patch
cd .. && ./compilar.sh          # gera OPL-RA-SMB.ELF
```

O `compilar.sh` faz o empacotamento à parte: o `ps2-packer` só acha o stub e o módulo rodando de dentro da pasta
dele (`/usr/local/ps2dev/share/ps2-packer/module`), então o último passo do Makefile do OPL falha sozinho.

Licença: a mesma do Open PS2 Loader (AFL-3.0).
