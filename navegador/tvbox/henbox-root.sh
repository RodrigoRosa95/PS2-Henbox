#!/system/bin/sh
# PS2 ligado direto no cabo da TV box (PS2 Henbox, 23/10/2026). Roda como root, em laço (5 s).
#
# Quando o cabo (eth0) tem sinal mas nenhum roteador dá IP nele por 30 s, a ponta é um PS2: a box, que está na
# internet pelo Wi-Fi, passa a levar o PS2 para a rede. Nada muda no PS2 (IP fixo do memory card/pendrive, em
# ps2nav/config.json):
#   - Wi-Fi na MESMA faixa do IP do PS2 → pseudo-ponte: proxy ARP nos dois lados e rota /32 para o PS2 no cabo.
#     Ponte de verdade com Wi-Fi cliente não existe (o Wi-Fi só aceita o endereço físico da própria box).
#   - Wi-Fi em OUTRA faixa (casa de amigo) → rede separada: o cabo assume o gateway que o PS2 espera e a box faz NAT.
# Nos dois modos: DHCP no cabo dando só o IP do PS2 (o OPL costuma usar DHCP) e a box continua atendendo também no IP
# que tinha no cabo (as configurações do PS2 apontam para ele: Samba do OPL, servidor do navegador).
# Desliga sozinho quando o cabo sai. Log: /data/local/henbox-rede/henbox-root.log. Forçar: echo desligado > .../modo
# Também mantém o motor do xeRAbora (conquistas, UDP 18194) ligado, se o app estiver instalado.
# Chamado pelo iniciar.sh (su) a cada início; só uma cópia roda (pid em .../pid).
H=/data/data/com.termux/files/home/ps2nav
PY=/data/data/com.termux/files/usr/bin/python3
EST=/data/local/henbox-rede
mkdir -p $EST; chmod 755 $EST
LOG=$EST/henbox-root.log
P=$(cat $EST/pid 2>/dev/null)
[ -n "$P" ] && grep -q henbox-root /proc/$P/cmdline 2>/dev/null && exit 0
echo $$ > $EST/pid
log() { echo "$(date '+%d/%m %H:%M:%S') $*" >> $LOG; }

v4() { ip -4 -o addr show "$1" 2>/dev/null | grep -v "${2:-^$}" | sed -n 's/.* inet \([0-9.]*\/[0-9]*\).*/\1/p' | head -1; }
gw_wifi() { ip route show table all 2>/dev/null | sed -n 's/^default via \([0-9.]*\) dev wlan0.*/\1/p' | head -1; }
tab_wifi() { ip route show table all 2>/dev/null | sed -n 's/^default via .* dev wlan0 table \([^ ]*\).*/\1/p' | head -1; }
ip2n() { echo "$1" | awk -F. '{print (($1*256+$2)*256+$3)*256+$4}'; }
mesma_rede() {   # mesma_rede IP1 IP2 PREFIXO
    local a b m
    a=$(ip2n "$1"); b=$(ip2n "$2")
    m=$(awk -v p="$3" 'BEGIN{print 2^32 - 2^(32-p)}')
    awk -v a="$a" -v b="$b" -v m="$m" 'BEGIN{exit !(int(a/(2^32-m+0)) == int(b/(2^32-m+0)))}'
}
pfx_de_mascara() { echo "$1" | awk -F. '{n=0; for(i=1;i<=4;i++){x=$i; while(x>0){n+=x%2; x=int(x/2)}} print n}'; }

config_ps2() {   # imprime "IP MÁSCARA GW" do config.json do pacote
    cd $H && HOME=/data/data/com.termux/files/home $PY -c \
        "import json;p=json.load(open('config.json'))['ps2'];print(p['ip'],p['mascara'],p['gw'])" 2>/dev/null
}

MARCA="henbox"   # rótulo nos endereços que o script põe, para achar e tirar depois

ligar() {
    W=$(v4 wlan0); WIP=${W%/*}; WPFX=${W#*/}; GW=$(gw_wifi); TAB=$(tab_wifi)
    set -- $(config_ps2)
    PS2=$1; MASK=$2; PGW=$3
    [ -n "$PS2" ] && [ -n "$WIP" ] || { log "sem IP do PS2 ou sem Wi-Fi: nada a fazer"; return 1; }
    PPFX=$(pfx_de_mascara $MASK)
    VELHO=$(cat $EST/ip-box-cabo 2>/dev/null)
    ip link set eth0 up
    echo 1 > /proc/sys/net/ipv4/ip_forward
    iptables -I FORWARD 1 -i eth0 -o wlan0 -j ACCEPT
    iptables -I FORWARD 1 -i wlan0 -o eth0 -j ACCEPT
    ip rule add iif eth0 lookup ${TAB:-main} prio 5000
    if mesma_rede $PS2 $WIP $WPFX; then
        MODO=ponte
        echo 1 > /proc/sys/net/ipv4/conf/wlan0/proxy_arp
        echo 1 > /proc/sys/net/ipv4/conf/eth0/proxy_arp
        # endereço da box no cabo (mesmo do Wi-Fi) como /32: sem rota de rede, a faixa continua sendo do Wi-Fi
        ip addr add $WIP/32 dev eth0 label eth0:$MARCA
        ip route add $PS2/32 dev eth0 table main
        [ -n "$TAB" ] && ip route add $PS2/32 dev eth0 table $TAB
        ip rule add to $PS2/32 lookup main prio 4999
        DGW=$GW
    else
        MODO=nat
        ip addr add $PGW/$PPFX dev eth0 label eth0:$MARCA
        iptables -t nat -A POSTROUTING -s $PS2/32 -o wlan0 -j MASQUERADE
        ip rule add to $PS2/32 lookup main prio 4999
        DGW=$PGW
    fi
    # o IP antigo da box no cabo continua valendo (Samba do OPL, servidor do navegador)
    [ -n "$VELHO" ] && [ "$VELHO" != "$WIP" ] && [ "$VELHO" != "$PGW" ] && ip addr add $VELHO/32 dev eth0 label eth0:$MARCA
    # DHCP só para o PS2 (o OPL costuma usar DHCP); o navegador e o PS2Link usam o IP fixo, que é o mesmo
    dnsmasq --interface=eth0 --bind-interfaces --except-interface=lo --port=0 --dhcp-authoritative \
        --dhcp-range=$PS2,$PS2,$MASK,12h --dhcp-option=3,$DGW --dhcp-option=6,${GW:-8.8.8.8} \
        --dhcp-leasefile=$EST/dhcp.leases --pid-file=$EST/dnsmasq.pid 2>> $LOG
    echo "$MODO $PS2 $WIP" > $EST/estado; chmod 644 $EST/estado
    log "LIGADO modo $MODO: PS2 $PS2 no cabo, box $WIP no Wi-Fi (gateway $GW, tabela ${TAB:-main})"
}

desligar() {
    motivo=$1
    [ -f $EST/dnsmasq.pid ] && kill $(cat $EST/dnsmasq.pid) 2>/dev/null
    rm -f $EST/dnsmasq.pid
    set -- $(cat $EST/estado 2>/dev/null)
    PS2=$2
    for a in $(ip -4 -o addr show eth0 | grep "eth0:$MARCA" | sed -n 's/.* inet \([0-9.]*\/[0-9]*\).*/\1/p'); do
        ip addr del $a dev eth0
    done
    if [ -n "$PS2" ]; then
        ip rule del to $PS2/32 lookup main prio 4999 2>/dev/null
        ip route del $PS2/32 dev eth0 table main 2>/dev/null
        T=$(tab_wifi); [ -n "$T" ] && ip route del $PS2/32 dev eth0 table $T 2>/dev/null
        iptables -t nat -D POSTROUTING -s $PS2/32 -o wlan0 -j MASQUERADE 2>/dev/null
    fi
    while ip rule del iif eth0 prio 5000 2>/dev/null; do :; done
    iptables -D FORWARD -i eth0 -o wlan0 -j ACCEPT 2>/dev/null
    iptables -D FORWARD -i wlan0 -o eth0 -j ACCEPT 2>/dev/null
    echo 0 > /proc/sys/net/ipv4/conf/wlan0/proxy_arp
    echo 0 > /proc/sys/net/ipv4/conf/eth0/proxy_arp
    rm -f $EST/estado
    log "desligado ($motivo)"
}

XERA=io.github.hacan359.xerabora
xerabora() {   # motor das conquistas: só o serviço (entra logado com o token salvo), sem abrir a tela
    grep -q ":4712 " /proc/net/udp /proc/net/udp6 2>/dev/null && return
    pm path $XERA >/dev/null 2>&1 || return
    am start-foreground-service -n $XERA/.EngineService >/dev/null 2>&1 && log "xeRAbora: motor religado"
}

log "vigia do cabo iniciado (pid $$)"
n=0
desligar "início" >/dev/null 2>&1
espera=0
while true; do
    car=$(cat /sys/class/net/eth0/carrier 2>/dev/null)
    pedido=$(cat $EST/modo 2>/dev/null)
    if [ -f $EST/estado ]; then
        if [ "$car" != 1 ] || [ "$pedido" = desligado ]; then
            desligar "cabo desconectado ou modo desligado"
        elif ! ip -4 -o addr show eth0 | grep -q "eth0:$MARCA"; then   # o Android tirou os endereços: refaz
            desligar "endereços sumiram"; ligar
        fi
    else
        e=$(v4 eth0 "eth0:$MARCA")
        if [ -n "$e" ]; then
            echo "${e%/*}" > $EST/ip-box-cabo   # o IP que a box tem no cabo com o roteador: o PS2 aponta para ele
            espera=0
        elif [ "$car" = 1 ] && [ "$pedido" != desligado ]; then
            espera=$((espera + 5))
            [ $espera -ge 30 ] && [ -n "$(v4 wlan0)" ] && { ligar; espera=0; }
        else
            espera=0
        fi
    fi
    n=$((n + 1)); [ $((n % 3)) = 1 ] && xerabora
    date +%s > $EST/vivo; chmod 644 $EST/vivo
    [ $(stat -c %s $LOG 2>/dev/null || echo 0) -gt 200000 ] && mv $LOG $LOG.1
    sleep 5
done
