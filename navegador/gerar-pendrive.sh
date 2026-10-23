#!/bin/bash
# Monta o pendrive.zip do PS2 (22/10/2026): o que vai na raiz de um pendrive FAT32 para o OPL.
#   APPS/NAVEGADOR_INICIAR/  PS2Link (ps2link-src, AFL 2.0) com o nome NAVEGADOR_INICIAR.ELF: a TV box acha o PS2Link na
#                            rede e abre o navegador por ele — o caminho que abre os jogos pela rede
#   APPS/NAVEGADOR/          navegador.elf direto (loja e cinema; "Jogar pela rede" trava aberto assim, ver memória)
#   ART/                     capas dos dois na aba Apps do OPL
# Uso: gerar-pendrive.sh [saída.zip]   (padrão: pendrive.zip aqui)
set -e
cd "$(dirname "$0")"
SAIDA=$(realpath -m "${1:-pendrive.zip}")
T=$(mktemp -d)
mkdir -p "$T/APPS/NAVEGADOR" "$T/APPS/NAVEGADOR_INICIAR" "$T/ART"
cp ps2/navegador.elf "$T/APPS/NAVEGADOR/navegador.elf"
printf 'title=PS2 Henbox (so loja e videos)\nboot=navegador.elf\n' > "$T/APPS/NAVEGADOR/title.cfg"
cp ps2/PS2LINK.ELF "$T/APPS/NAVEGADOR_INICIAR/NAVEGADOR_INICIAR.ELF"
printf 'title=PS2 Henbox\nboot=NAVEGADOR_INICIAR.ELF\n' > "$T/APPS/NAVEGADOR_INICIAR/title.cfg"
printf '192.168.4.230 255.255.255.0 192.168.4.1\n' > "$T/APPS/NAVEGADOR_INICIAR/IPCONFIG.DAT"
cp capa/navegador.elf_COV.jpg "$T/ART/navegador.elf_COV.jpg"
cp capa/navegador.elf_COV.jpg "$T/ART/NAVEGADOR_INICIAR.ELF_COV.jpg"
cat > "$T/APPS/NAVEGADOR/LEIA-ME.txt" <<'TXT'
PS2 Henbox — Navegador do PS2
Jeito mais fácil: espete este pendrive na USB da TV box e use "Preparar pendrive do PS2" no app PS2 Henbox — a box
copia tudo com o IP certo. Pelo PC: copie as pastas APPS e ART para a raiz de um pendrive FAT32.
No PS2: OPL → Apps → "PS2 Henbox". A TV box encontra o PS2 e abre o navegador sozinha em poucos segundos.
"PS2 Henbox (so loja e videos)" abre o navegador direto (os jogos pela rede não abrem por ele).
O IP do PS2 fica no IPCONFIG.DAT ("IP MÁSCARA GATEWAY"); a TV box mantém esse arquivo certo sozinha a cada conexão.
Com o PS2 ligado direto no cabo da TV box, o IP nem precisa ser da rede de casa: a box leva o PS2 para a internet.
https://github.com/RodrigoRosa95/PS2-Henbox
TXT
cat > "$T/APPS/NAVEGADOR_INICIAR/LEIA-ME.txt" <<'TXT'
NAVEGADOR_INICIAR.ELF é o PS2Link (ps2dev, Academic Free License 2.0), sem modificações, só com outro nome:
https://github.com/ps2dev/ps2link — a TV box usa o PS2Link para abrir o navegador do PS2.
O IP vem do IPCONFIG.DAT desta pasta ("IP MÁSCARA GATEWAY").
TXT
cp ps2link-src/LICENSE "$T/APPS/NAVEGADOR_INICIAR/LICENSE-PS2LINK.txt"
rm -f "$SAIDA"
(cd "$T" && zip -q -r -X "$SAIDA" APPS ART)
rm -rf "$T"
unzip -l "$SAIDA"
