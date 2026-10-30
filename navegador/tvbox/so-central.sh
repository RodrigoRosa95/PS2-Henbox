#!/data/data/com.termux/files/usr/bin/bash
# só a central do celular (porta 8785)
cd ~/ps2nav
nohup python3 central.py 8785 > central.log 2>&1 &
