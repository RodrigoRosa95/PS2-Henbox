#!/bin/bash
# Servidor em nuvem do ps2GamesCLoudinOPl num PC Linux, com um comando:
#   servidor/instalar.sh /caminho/da/colecao [IP_DA_TV_BOX]
# A coleção é uma pasta com DVD/ e CD/ (ISOs de PS2) e, se quiser, VIDEOS-PS2/ (vídeos já convertidos para o PS2).
# Liga 2 serviços (PM2 se existir, senão systemd do usuário) e mostra o endereço e a chave para pôr no app do celular:
#   loja (servidor.py, porta 8770) e vídeos/ROMs/ISOs/loja para a TV box (navegador/videos_https.py, porta 8781).
# Para acessar de fora de casa: túnel Cloudflare (ou outro HTTPS) apontando para a porta 8781 — ver docs/instalacao.md.
set -e
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
COLECAO=${1:?uso: servidor/instalar.sh /caminho/da/colecao [IP_DA_TV_BOX]}
COLECAO=$(cd "$COLECAO" && pwd)
TVBOX=${2:-}
mkdir -p "$COLECAO/DVD" "$COLECAO/CD" "$COLECAO/VIDEOS-PS2"

command -v python3 >/dev/null || { echo "Instale o Python 3 (ex.: sudo apt install python3)"; exit 1; }
python3 -c 'import PIL' 2>/dev/null || echo "Aviso: sem o Pillow (sudo apt install python3-pil) as capas do cinema não são geradas."

ENV="$RAIZ/servidor/servidor.env"
cat > "$ENV" <<CFG
PS2_JOGOS=$COLECAO
PS2_VIDEOS=$COLECAO/VIDEOS-PS2
PS2_TVBOX=${TVBOX:-127.0.0.1}
PS2_NAV_IP=${TVBOX:-127.0.0.1}
CFG
CHAVE="$RAIZ/navegador/videos_https.chave"
[ -s "$CHAVE" ] || (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$CHAVE")

if command -v pm2 >/dev/null; then
    set -a; . "$ENV"; set +a
    pm2 delete ps2-web ps2-videos >/dev/null 2>&1 || true
    pm2 start "$RAIZ/servidor.py" --name ps2-web --interpreter python3 --cwd "$RAIZ" >/dev/null
    pm2 start "$RAIZ/navegador/videos_https.py" --name ps2-videos --interpreter python3 --cwd "$RAIZ/navegador" >/dev/null
    pm2 save >/dev/null
    echo "Serviços ligados no PM2 (pm2 status). Para subir com o PC: pm2 startup"
else
    U=~/.config/systemd/user; mkdir -p "$U"
    for s in "ps2-web:$RAIZ/servidor.py:$RAIZ" "ps2-videos:$RAIZ/navegador/videos_https.py:$RAIZ/navegador"; do
        IFS=: read -r nome prog dir <<<"$s"
        cat > "$U/$nome.service" <<UNIT
[Unit]
Description=ps2GamesCLoudinOPl $nome
After=network-online.target
[Service]
EnvironmentFile=$ENV
WorkingDirectory=$dir
ExecStart=/usr/bin/env python3 $prog
Restart=always
[Install]
WantedBy=default.target
UNIT
    done
    systemctl --user daemon-reload
    systemctl --user enable --now ps2-web ps2-videos
    echo "Serviços ligados no systemd do usuário (systemctl --user status ps2-web ps2-videos)."
    echo "Para rodarem sem login: sudo loginctl enable-linger $USER"
fi

IP=$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[\d.]+' || hostname -I | awk '{print $1}')
echo
echo "Pronto. No app do celular (InstaladorPS2), em Servidor em nuvem:"
echo "  Endereço: http://$IP:8781"
echo "  Chave:    $(cat "$CHAVE")"
echo "Coleção: $COLECAO (ponha os ISOs em DVD/ e CD/)."
