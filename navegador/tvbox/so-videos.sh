#!/data/data/com.termux/files/usr/bin/bash
# só a página de vídeos/loja (porta 8780)
cd ~/ps2nav
nohup python3 videos.py 8780 > videos.log 2>&1 &
