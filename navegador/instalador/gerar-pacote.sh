#!/bin/bash
# Monta os arquivos que o app instalador (celular) leva para a TV box (pedido do usuário 17/10/2026).
#   assets/ps2nav.tar.gz   ~/ps2nav (servidores, scripts, fontes, ps2/ com navegador.elf, Neutrino, SNESticle, SMS),
#                          ~/udpfs_server (servidor oficial do Neutrino) e os scripts do Termux:Boot
#   assets/*.apk           PS2 Navegador (WebView da box), Termux e Termux:Boot (terceiros/, builds oficiais)
# Leva config.json com os endereços do notebook e a chave do videos_https.py: só para as boxes do próprio usuário.
# ROMs e vídeos ficam de fora (a loja baixa a ROM do notebook quando precisa).
set -e
cd "$(dirname "$0")"
N=..; T=$(mktemp -d)
mkdir -p "$T/ps2nav/ps2" "$T/ps2nav/fontes" "$T/boot" assets
cp $N/{navegador_servidor,servidor_host,videos,udpfs_nuvem,configurar}.py "$T/ps2nav/"
cp $N/tvbox/{iniciar,so-host,so-navegador,so-videos}.sh "$T/ps2nav/"
cp $N/tvbox/boot-ps2nav.sh "$T/boot/ps2nav"; cp $N/tvbox/udpfs-ps2.sh "$T/boot/udpfs-ps2.sh"
cp /usr/share/fonts/truetype/dejavu/DejaVuSans{,-Bold}.ttf "$T/ps2nav/fontes/"
cp $N/ps2/{clique.raw,musica.raw,navegador.elf} "$T/ps2nav/ps2/"
cp -r $N/ps2/opl $N/ps2/sms $N/ps2/snesticle "$T/ps2nav/ps2/"
cp -r ../../neutrino "$T/ps2nav/ps2/neutrino"
mkdir -p "$T/udpfs_server"; cp -r ../../udpfs_server/udpfs_server.py ../../udpfs_server/compressed_iso "$T/udpfs_server/"
find "$T" -name __pycache__ -prune -exec rm -rf {} +
find "$T" \( -name "*.bak*" -o -name "*.antes-*" \) -delete
python3 - "$T/ps2nav/config.json" <<'PY'
import json, sys
chave = open('../videos_https.chave').read().strip()
json.dump({'ps2': {'ip': '192.168.4.230', 'mascara': '255.255.255.0', 'gw': '192.168.4.1'},
           'notebook': {'urls': ['http://192.168.4.135:8781', 'https://ps2videos.rodrigoflix.com'], 'chave': chave,
                        'casa': 'http://192.168.4.135:8770'}}, open(sys.argv[1], 'w'), indent=1)
PY
date +%Y%m%d-%H%M > "$T/ps2nav/VERSAO"
tar -czf assets/ps2nav.tar.gz -C "$T" ps2nav udpfs_server boot
cp ../tvbox-app/PS2Navegador.apk assets/
cp terceiros/termux-app_v0.118.3+github-debug_armeabi-v7a.apk assets/termux-armeabi-v7a.apk
cp terceiros/termux-app_v0.118.3+github-debug_arm64-v8a.apk assets/termux-arm64-v8a.apk
cp terceiros/termux-boot-app_v0.8.1+github.debug.apk assets/termux-boot.apk
cp "$T/ps2nav/VERSAO" assets/VERSAO
rm -rf "$T"
ls -l assets
