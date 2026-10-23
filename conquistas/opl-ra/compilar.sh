#!/bin/bash
# OPL-RA (xeRAbora) com abertura direta por SMB para o navegador.elf (23/10/2026).
# Fonte: opl/ (fork hacan359/Open-PS2-Loader, branch ra + branch local smb-autolaunch).
# PADEMU=1: mantém DS3/DS4 por Bluetooth dentro do jogo (o build oficial do xeRAbora usa PADEMU=0).
# Saída: OPL-RA-SMB.ELF. O ps2-packer daqui só acha o stub e o módulo rodando de dentro da pasta dele,
# por isso o último passo do Makefile (OPNPS2LD.ELF) falha e o empacotamento é feito à parte.
set -e
AQUI=$(cd "$(dirname "$0")" && pwd)
cd "$AQUI/opl"
source /usr/local/ps2dev/env.sh
[ -d lng_src ] || make download_lng download_lwNBD
make PADEMU=1 all -j6 > "$AQUI/build.log" 2>&1 || grep -q "OPNPS2LD.ELF\] Erro" "$AQUI/build.log"
cd /usr/local/ps2dev/share/ps2-packer/module
ps2-packer -s ../stub/lzma-1d00-stub "$AQUI/opl/opl_stripped.elf" "$AQUI/OPL-RA-SMB.ELF" | tail -1
