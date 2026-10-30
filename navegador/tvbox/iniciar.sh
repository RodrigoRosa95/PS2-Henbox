#!/data/data/com.termux/files/usr/bin/bash
# Navegador do PS2 na TV box (17/10/2026). Liga o app (WebView) e os servidores; chamado pelo Termux:Boot
# (~/.termux/boot/ps2nav) ou pelo app instalador do celular. Logs em ~/ps2nav/*.log
#   servidor_host.py      host: do PS2 (porta 0x4721 no PS2) servindo ~/ps2nav/ps2
#   videos.py             página inicial (8780): Loja + Vídeos (vídeos/loja/ROMs/ISOs do notebook por remoto.json)
#   central.py            central do celular (8785): capas, arquivos do PS2/box, controle remoto, ISOs do celular, kits
#   navegador_servidor.py WebView do app pelo DevTools (9222) + quadros (9223) → tela do PS2
#   udpfs_nuvem.py        jogos do Neutrino (pendrive da box ou "nuvem"), em ~/.termux/boot/udpfs-ps2.sh
#   henbox-root.sh        (root) PS2 ligado direto no cabo da box + motor do xeRAbora
#   atualizar.py          confere se há pacote novo publicado e se atualiza
# IP do PS2 e endereços do notebook: config.json (configurar.py).
cd ~/ps2nav
# Termux:Boot e o app PS2 Navegador (no boot) chamam ao mesmo tempo: só um segue (trava de 60 s)
if ! mkdir ~/.ps2nav-iniciando 2>/dev/null; then
    [ $(( $(date +%s) - $(stat -c %Y ~/.ps2nav-iniciando) )) -lt 60 ] && exit 0
fi
trap 'rmdir ~/.ps2nav-iniciando 2>/dev/null' EXIT
python3 configurar.py aplicar > /dev/null
PS2=$(python3 configurar.py ip-ps2)
# ps2/jogos-box → DVD/ do pendrive/HD de jogos da box (conquistas e "copiar para o PS2"), achado sozinho
JOGOS=$(for d in /storage/*-*; do [ -d "$d/DVD" ] && echo "$d/DVD"; done 2>/dev/null | head -1)
[ -n "$JOGOS" ] && [ "$(readlink ps2/jogos-box)" != "$JOGOS" ] && ln -sfn "$JOGOS" ps2/jogos-box
am start -n br.ps2nav/.Inicio >/dev/null 2>&1
sleep 5
termux-wake-lock 2>/dev/null
# pelo PID: o pkill/pgrep do Termux nem sempre acha os processos (o [x] no padrão não pega o próprio grep)
pids() { /system/bin/ps -A -o PID,ARGS | grep -E "$1" | awk '{print $1}'; }
for p in $(pids '[s]ervidor_host.py|[n]avegador_servidor.py|[v]ideos.py 8780|[c]entral.py'); do kill $p; done
sleep 1
nohup python3 servidor_host.py "$PS2" > host.log 2>&1 &
nohup python3 videos.py 8780 > videos.log 2>&1 &
nohup python3 central.py 8785 > central.log 2>&1 &   # central do celular (capas, arquivos, controle, ISOs, kits)
PS2_NAV_CDP=127.0.0.1:9222 PS2_NAV_QUADROS=127.0.0.1:9223 PS2_NAV_CONTROLE_IP=0.0.0.0 \
PS2_NAV_INICIO=http://127.0.0.1:8780/ PS2_NAV_LOJA=http://127.0.0.1:8780/loja/loja.html PS2_NAV_CINEMA= \
    nohup python3 navegador_servidor.py > navegador.log 2>&1 &
[ -n "$(pids '[u]dpfs_nuvem.py')" ] || sh ~/.termux/boot/udpfs-ps2.sh
# root (23/10/2026): PS2 direto no cabo da box (ponte/NAT) + motor do xeRAbora; só uma cópia roda
su -c "nohup sh $HOME/ps2nav/henbox-root.sh >/dev/null 2>&1 &" 2>/dev/null
# atualização automática do pacote pela pasta downloads/ do GitHub (desligada com "atualizar": false no config.json)
for p in $(pids "[a]tualizar.py"); do kill $p; done
nohup python3 atualizar.py >> atualizar.log 2>&1 &
