#!/bin/bash
# Monta os arquivos que o app instalador (celular) leva para a TV box (pedido do usuário 17/10/2026).
#   assets/ps2nav.tar.gz   ~/ps2nav (servidores, scripts, fontes, ps2/ com navegador.elf, Neutrino, SNESticle, SMS),
#                          ~/udpfs_server (servidor oficial do Neutrino) e os scripts do Termux:Boot
#   assets/*.apk           PS2 Navegador (WebView da box), Termux e Termux:Boot (terceiros/, builds oficiais)
# Leva config.json com os endereços do notebook e a chave do videos_https.py: só para as boxes do próprio usuário.
# ROMs e vídeos ficam de fora (a loja baixa a ROM do notebook quando precisa).
# PUBLICO=1 (18/10/2026, Release do GitHub): sem os endereços de casa (o app pergunta o servidor) e sem o SMS/SNESticle
# (licenças sem redistribuição clara), com o aviso de licença do Neutrino (AFL-3.0). Desde o 24/10/2026 vem com o
# acesso de leitura ao catálogo do autor por HTTPS (jogar em nuvem): chave especial do painel em chave-publica.txt.
# CONVIDADO=<json do painel de chaves> (22/10/2026): igual ao público, mas já com o HTTPS e a chave extra do convidado
# (revogável no painel) — sem os endereços de casa. Baixado em /instalador?chave=… do videos_https.py.
[ -n "$CONVIDADO" ] && PUBLICO=1
set -e
cd "$(dirname "$0")"
N=..; T=$(mktemp -d)
mkdir -p "$T/ps2nav/ps2" "$T/ps2nav/fontes" "$T/boot" assets
cp $N/{navegador_servidor,servidor_host,videos,udpfs_nuvem,configurar,nuvem,atualizar,ra_hash,ra_preparar,central}.py $N/central.html $N/central-compat.html "$T/ps2nav/"
cp $N/tvbox/{iniciar,so-host,so-navegador,so-videos,so-central,henbox-root,preparar-pendrive}.sh "$T/ps2nav/"
cp $N/tvbox/boot-ps2nav.sh "$T/boot/ps2nav"; cp $N/tvbox/udpfs-ps2.sh "$T/boot/udpfs-ps2.sh"
cp /usr/share/fonts/truetype/dejavu/DejaVuSans{,-Bold}.ttf "$T/ps2nav/fontes/"
cp $N/ps2/{clique.raw,navegador.elf} "$T/ps2nav/ps2/"
# 🏆 conquistas: OPL-RA do Henbox (fork AFL-3.0 do OPL do xeRAbora; patches em conquistas/opl-ra/ no GitHub) e os sons
mkdir -p "$T/ps2nav/ps2/oplra" "$T/ps2nav/ps2/sons"
cp ../../opl-ra/OPL-RA-SMB.ELF "$T/ps2nav/ps2/oplra/"
cp $N/sons/*.raw "$T/ps2nav/ps2/sons/"
# 🎵 música de fundo da loja: o pacote vai sem nenhuma (pedido do usuário 24/10/2026); quem quiser põe os próprios
# MP3 na pasta MUSICAS do pendrive da box (videos.py converte)
# pendrive do PS2 pronto (APPS + ART), para o "Preparar pendrive" na USB da própria box
$N/gerar-pendrive.sh "$T/pendrive.zip" > /dev/null
mkdir -p "$T/ps2nav/pendrive" && (cd "$T/ps2nav/pendrive" && unzip -q ../../pendrive.zip) && rm "$T/pendrive.zip"
if [ "$PUBLICO" = 1 ]; then cp -r $N/ps2/opl "$T/ps2nav/ps2/"; else cp -r $N/ps2/opl $N/ps2/sms $N/ps2/snesticle "$T/ps2nav/ps2/"; fi
cp -r ../../neutrino "$T/ps2nav/ps2/neutrino"
cat > "$T/ps2nav/ps2/neutrino/LEIA-ME.txt" <<'AVISO'
Neutrino v1.8.0 (c) Maximus32 / rickgaiser, sem modificações — licença Academic Free License 3.0 (AFL-3.0).
Código-fonte e licença: https://github.com/rickgaiser/neutrino
Acrescentados: config/pademu.toml e modules/bt_pademu.irx = PadEmu do Open PS2 Loader (AFL-3.0,
https://github.com/ps2homebrew/Open-PS2-Loader, modules/pademu), para o DualShock 3/4 por Bluetooth nos jogos.
As configurações em config/ ganham o IP do PS2 (configurar.py).
AVISO
mkdir -p "$T/udpfs_server"; cp -r ../../udpfs_server/udpfs_server.py ../../udpfs_server/compressed_iso "$T/udpfs_server/"
find "$T" -name __pycache__ -prune -exec rm -rf {} +
find "$T" \( -name "*.bak*" -o -name "*.antes-*" \) -delete
python3 - "$T/ps2nav/config.json" "$PUBLICO" "$CONVIDADO" <<'PY'
import json, sys
if sys.argv[3]:
    c = json.load(open(sys.argv[3]))['chave']
    json.dump({'ps2': {'ip': '192.168.4.230', 'mascara': '255.255.255.0', 'gw': '192.168.4.1'},
               'notebook': {'urls': ['https://ps2videos.rodrigoflix.com'], 'chave': c['chave'] if isinstance(c, dict) else c,
                            'casa': ''}}, open(sys.argv[1], 'w'), indent=1)
    sys.exit()
if sys.argv[2] == '1':
    # APK público: já com acesso ao catálogo do autor por HTTPS (jogar em nuvem). A chave é uma especial do painel
    # (chaves.py), revogável na hora sem afetar a principal; o arquivo chave-publica.txt não vai para o GitHub.
    try:
        publico_chave = open('chave-publica.txt').read().strip()
    except OSError:
        sys.exit('gerar-pacote: crie instalador/chave-publica.txt (painel de chaves) antes do build público.')
    if not publico_chave:
        sys.exit('gerar-pacote: instalador/chave-publica.txt vazia (crie uma chave no painel).')
    json.dump({'ps2': {'ip': '192.168.4.230', 'mascara': '255.255.255.0', 'gw': '192.168.4.1'},
               'notebook': {'urls': ['https://ps2videos.rodrigoflix.com'], 'chave': publico_chave, 'casa': ''}},
              open(sys.argv[1], 'w'), indent=1)
    sys.exit()
chave = open('../videos_https.chave').read().strip()
json.dump({'ps2': {'ip': '192.168.4.230', 'mascara': '255.255.255.0', 'gw': '192.168.4.1'}, 'atualizar': False,
           'notebook': {'urls': ['http://192.168.4.135:8781', 'https://ps2videos.rodrigoflix.com'], 'chave': chave,
                        'casa': 'http://192.168.4.135:8770'}}, open(sys.argv[1], 'w'), indent=1)
PY
date +%Y%m%d-%H%M > "$T/ps2nav/VERSAO"
tar -czf assets/ps2nav.tar.gz -C "$T" ps2nav udpfs_server boot
# público: também o pacote da atualização automática (atualizar.py), sem config.json, para a pasta downloads/ do GitHub
if [ "$PUBLICO" = 1 ] && [ -z "$CONVIDADO" ]; then
    rm "$T/ps2nav/config.json"
    tar -czf sai-ps2nav-atualizacao.tar.gz -C "$T" ps2nav udpfs_server boot
    echo "$(cat "$T/ps2nav/VERSAO") $(sha256sum sai-ps2nav-atualizacao.tar.gz | cut -d' ' -f1)" > sai-ps2nav-versao.txt
fi
cp ../tvbox-app/PS2Navegador.apk assets/
cp terceiros/termux-app_v0.118.3+github-debug_armeabi-v7a.apk assets/termux-armeabi-v7a.apk
cp terceiros/termux-app_v0.118.3+github-debug_arm64-v8a.apk assets/termux-arm64-v8a.apk
cp terceiros/termux-boot-app_v0.8.1+github.debug.apk assets/termux-boot.apk
cp "$T/ps2nav/VERSAO" assets/VERSAO
rm -rf "$T"
ls -l assets
