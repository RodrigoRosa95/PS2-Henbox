#!/data/data/com.termux/files/usr/bin/bash
# só o navegador_servidor.py (sem reiniciar o host: nem a página de vídeos)
cd ~/ps2nav
PS2_NAV_CDP=127.0.0.1:9222 PS2_NAV_QUADROS=127.0.0.1:9223 PS2_NAV_CONTROLE_IP=0.0.0.0 \
PS2_NAV_INICIO=http://127.0.0.1:8780/ PS2_NAV_LOJA=http://127.0.0.1:8780/loja/loja.html PS2_NAV_CINEMA= \
    nohup python3 navegador_servidor.py > navegador.log 2>&1 &
