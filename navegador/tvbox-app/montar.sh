#!/bin/bash
# Monta o PS2Navegador.apk sem Gradle (aapt + javac + dx + apksigner do /usr/lib/android-sdk). ./montar.sh
set -e
cd "$(dirname "$0")"
SDK=${ANDROID_SDK:-/usr/lib/android-sdk}; BT=$SDK/build-tools/29.0.3; JAR=$SDK/platforms/android-23/android.jar
rm -rf obj sai && mkdir -p obj sai
javac --release 8 -nowarn -cp "$JAR" -d obj $(find src -name '*.java')
$BT/dx --dex --min-sdk-version=21 --output=sai/classes.dex obj
$BT/aapt package -f -M AndroidManifest.xml -I "$JAR" -F sai/base.apk
(cd sai && $BT/aapt add base.apk classes.dex >/dev/null)
$BT/zipalign -f 4 sai/base.apk sai/alinhado.apk
[ -f chave.jks ] || keytool -genkeypair -keystore chave.jks -storepass ps2nav1 -keypass ps2nav1 -alias ps2nav \
    -keyalg RSA -keysize 2048 -validity 20000 -dname "CN=PS2 Navegador" >/dev/null 2>&1
$BT/apksigner sign --ks chave.jks --ks-pass pass:ps2nav1 --out PS2Navegador.apk sai/alinhado.apk
ls -l PS2Navegador.apk
