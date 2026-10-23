#!/bin/bash
# Monta o APK "PS2 Conquistas" (PS2 Henbox) sem Gradle: javac + dx + aapt + apksigner (android-sdk do apt, plataforma 23).
#   ./montar.sh                       → PS2Conquistas.apk; o app acha a TV box sozinho na rede (GET :8780/henbox)
#   TVBOX_PADRAO=192.168.0.50 ./montar.sh → já vem com esse endereço (a busca automática continua valendo)
# A chave fica fora do projeto (~/.config/henbox-conquistas/); sem ela as atualizações não instalam por cima.
set -e
cd "$(dirname "$0")"
SDK=/usr/lib/android-sdk
JAR=$SDK/platforms/android-23/android.jar
BT=$SDK/build-tools/29.0.3
TVBOX=${TVBOX_PADRAO:-}
SAIDA=PS2Conquistas.apk
OBRA=$(mktemp -d)
trap 'rm -rf "$OBRA"' EXIT
CHAVE=$HOME/.config/henbox-conquistas/assinatura.jks
SENHA_ARQ=$HOME/.config/henbox-conquistas/senha
if [ ! -f "$CHAVE" ]; then
    mkdir -p "$(dirname "$CHAVE")"; chmod 700 "$(dirname "$CHAVE")"
    head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$SENHA_ARQ"; chmod 600 "$SENHA_ARQ"
    keytool -genkeypair -keystore "$CHAVE" -alias henbox -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass "$(cat "$SENHA_ARQ")" -keypass "$(cat "$SENHA_ARQ")" -dname "CN=PS2 Henbox" >/dev/null 2>&1
fi
mkdir -p "$OBRA/classes" "$OBRA/gerado/br/henbox/conquistas"
cat > "$OBRA/gerado/br/henbox/conquistas/BuildConfigHenbox.java" <<EOF
package br.henbox.conquistas;
/** Gerado pelo montar.sh: endereço da TV box já preenchido (vazio na versão pública). */
final class BuildConfigHenbox { static final String TVBOX_PADRAO = "$TVBOX"; }
EOF
javac -encoding UTF-8 -source 8 -target 8 -bootclasspath "$JAR" -Xlint:-options -d "$OBRA/classes" \
    $(find src "$OBRA/gerado" -name '*.java')
"$BT/dx" --dex --min-sdk-version=19 --output="$OBRA/classes.dex" "$OBRA/classes"
"$BT/aapt" package -f -M AndroidManifest.xml -S res -I "$JAR" -F "$OBRA/sem-codigo.apk"
(cd "$OBRA" && cp sem-codigo.apk sem-assinatura.apk && "$BT/aapt" add sem-assinatura.apk classes.dex >/dev/null)
"$BT/zipalign" -f 4 "$OBRA/sem-assinatura.apk" "$OBRA/alinhado.apk"
"$BT/apksigner" sign --ks "$CHAVE" --ks-pass "file:$SENHA_ARQ" --out "$SAIDA" "$OBRA/alinhado.apk"
rm -f "$SAIDA.idsig"
echo "$SAIDA ($(du -h "$SAIDA" | cut -f1))"
