#!/data/data/com.termux/files/usr/bin/bash
# só o host: do PS2 (servidor_host.py), com o IP do config.json
cd ~/ps2nav
nohup python3 servidor_host.py "$(python3 configurar.py ip-ps2)" > host.log 2>&1 &
