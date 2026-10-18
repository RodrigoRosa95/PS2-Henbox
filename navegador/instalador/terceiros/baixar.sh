#!/bin/bash
# Baixa os APKs oficiais do Termux e do Termux:Boot (GPLv3, github.com/termux) e confere o SHA-256.
set -e
cd "$(dirname "$0")"
B=https://github.com/termux/termux-app/releases/download/v0.118.3
for f in "termux-app_v0.118.3+github-debug_armeabi-v7a.apk" "termux-app_v0.118.3+github-debug_arm64-v8a.apk" "termux-app_v0.118.3+github-debug_sha256sums"; do
    curl -fsSL -o "$f" "$B/$f"
done
curl -fsSL -o "termux-boot-app_v0.8.1+github.debug.apk" https://github.com/termux/termux-boot/releases/download/v0.8.1/termux-boot-app_v0.8.1+github.debug.apk
curl -fsSL -o boot-checksums.txt https://github.com/termux/termux-boot/releases/download/v0.8.1/checksums-sha256.txt
sha256sum -c --ignore-missing "termux-app_v0.118.3+github-debug_sha256sums"
sha256sum -c --ignore-missing boot-checksums.txt
