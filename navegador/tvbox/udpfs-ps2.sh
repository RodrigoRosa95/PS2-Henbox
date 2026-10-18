#!/data/data/com.termux/files/usr/bin/sh
# Servidor de jogos do Neutrino rodando na TV box (vai em ~/.termux/boot/): ISOs do pendrive da box e, se o ISO não
# estiver lá, do HD do notebook por HTTPS ("jogo em nuvem", ~/ps2nav/udpfs_nuvem.py + remoto.json). Porta UDP 62966.
USB=$(ls -d /storage/*-* 2>/dev/null | head -1)
[ -n "$USB" ] || { mkdir -p ~/ps2nav/jogos/DVD ~/ps2nav/jogos/CD; USB=~/ps2nav/jogos; }   # sem pendrive: só nuvem
pkill -f udpfs_server.py 2>/dev/null; pkill -f udpfs_nuvem.py 2>/dev/null; sleep 1
cd ~/udpfs_server && nohup python -u ~/ps2nav/udpfs_nuvem.py -d "$USB" --read-only > ~/udpfs.log 2>&1 &
echo "udpfs (com nuvem) em $USB" > ~/udpfs.status
