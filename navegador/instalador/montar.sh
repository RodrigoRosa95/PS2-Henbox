#!/bin/bash
# Monta o InstaladorPS2.apk (celular) sem Gradle: gerar-pacote.sh (assets da TV box) + aapt + javac + dx + apksigner.
# A chave de assinatura é a mesma do app da box (../tvbox-app/chave.jks).
set -e
cd "$(dirname "$0")"
./gerar-pacote.sh > /dev/null
SDK=/usr/lib/android-sdk; BT=$SDK/build-tools/29.0.3; JAR=$SDK/platforms/android-23/android.jar
rm -rf obj sai && mkdir -p obj sai
javac --release 8 -nowarn -cp "$JAR" -d obj $(find src -name '*.java')
$BT/dx --dex --min-sdk-version=16 --output=sai/classes.dex obj
$BT/aapt package -f -0 apk -0 gz -M AndroidManifest.xml -I "$JAR" -A assets -F sai/base.apk
(cd sai && $BT/aapt add base.apk classes.dex >/dev/null)
zipalign -f 4 sai/base.apk sai/alinhado.apk
apksigner sign --ks ../tvbox-app/chave.jks --ks-pass pass:ps2nav1 --out InstaladorPS2.apk sai/alinhado.apk
ls -l InstaladorPS2.apk
