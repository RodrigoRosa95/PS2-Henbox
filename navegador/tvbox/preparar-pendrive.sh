#!/system/bin/sh
# Prepara o pendrive do PS2 na USB da própria TV box (PS2 Henbox, 23/10/2026): sem PC.
# Roda como root (o instalador chama por su). Copia ~/ps2nav/pendrive/ (APPS e ART do pendrive.zip) e o IPCONFIG.DAT
# certo desta box (ps2/IPCONFIG.DAT, do configurar.py) para as duas pastas do navegador.
#   preparar-pendrive.sh listar                 → uma linha por pendrive: ID|tamanho MB|livre MB|tem ISO (sim/não)|pastas
#   preparar-pendrive.sh preparar ID            → só copia (o que já estiver no pendrive fica)
#   preparar-pendrive.sh preparar ID formatar   → APAGA TUDO, formata em FAT32 (vfat do Android) e copia
# Por segurança não formata pendrive com ISO (é o HD/pendrive de jogos da box).
H=/data/data/com.termux/files/home/ps2nav
ORIGEM=$H/pendrive
volumes() { sm list-volumes public 2>/dev/null | awk '$2 == "mounted" {print $1 "|" $3}'; }
pasta_de() { echo /mnt/media_rw/$1; }
tem_iso() { [ -n "$(find "$1" -maxdepth 3 -iname '*.iso' 2>/dev/null | head -1)" ] && echo sim || echo não; }

case "$1" in
listar)
    for v in $(volumes); do
        id=$(echo "$v" | cut -d'|' -f2); d=$(pasta_de $id)
        set -- $(df -k "$d" | tail -1)
        echo "$id|$(($2 / 1024))|$(($4 / 1024))|$(tem_iso "$d")|$(ls "$d" 2>/dev/null | head -8 | tr '\n' ' ')"
    done
    ;;
preparar)
    ID=$2; [ -n "$ID" ] || { echo "ERRO: falta o ID do pendrive (use listar)"; exit 1; }
    VOL=$(volumes | grep "|$ID\$" | cut -d'|' -f1)
    [ -n "$VOL" ] || { echo "ERRO: pendrive $ID não encontrado"; exit 1; }
    [ -d "$ORIGEM/APPS" ] || { echo "ERRO: falta $ORIGEM (pacote antigo? atualize pelo instalador)"; exit 1; }
    if [ "$3" = formatar ]; then
        [ "$(tem_iso "$(pasta_de $ID)")" = sim ] && { echo "ERRO: este pendrive tem ISOs; não formato (apague-as antes)"; exit 1; }
        MAI=$(echo $VOL | cut -d: -f2 | cut -d, -f1); MEN=$(echo $VOL | cut -d, -f2)
        DISCO=disk:$MAI,$((MEN - MEN % 16))   # public:8,17 (sdb1) → disk:8,16 (sdb)
        sm list-disks 2>/dev/null | grep -qx "$DISCO" || { echo "ERRO: disco $DISCO não encontrado"; exit 1; }
        ANTES=$(volumes | cut -d'|' -f2 | grep -v "^$ID\$")
        echo "Formatando $DISCO em FAT32…"
        sm partition $DISCO public || { echo "ERRO: a formatação falhou"; exit 1; }
        for i in $(seq 1 30); do   # o Android monta de novo com outro ID
            sleep 1; NOVO=$(volumes | cut -d'|' -f2 | grep -v -x -F "$ANTES" | head -1); [ -n "$NOVO" ] && break
        done
        [ -n "$NOVO" ] || { echo "ERRO: o pendrive não voltou depois de formatar"; exit 1; }
        ID=$NOVO
    fi
    D=$(pasta_de $ID)
    echo "Copiando para o pendrive $ID…"
    cp -r $ORIGEM/. "$D/" || { echo "ERRO: a cópia falhou"; exit 1; }
    for p in NAVEGADOR NAVEGADOR_INICIAR; do
        [ -d "$D/APPS/$p" ] && cp $H/ps2/IPCONFIG.DAT "$D/APPS/$p/IPCONFIG.DAT"
    done
    sync
    echo "OK $ID: $(cat $H/ps2/IPCONFIG.DAT 2>/dev/null) — pode tirar o pendrive e pôr na USB da frente do PS2"
    ;;
*)
    echo "uso: $0 listar | preparar ID [formatar]"; exit 1
    ;;
esac
