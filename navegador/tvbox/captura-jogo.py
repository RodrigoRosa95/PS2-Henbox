#!/data/data/com.termux/files/usr/bin/python3
"""Grava as partidas online do PS2 (23/10/2026, placar do evento online — passo 1: descobrir onde está o placar).

Com o PS2 direto no cabo da TV box (henbox-root.sh, modo ponte ou NAT), todo o tráfego dele passa pela box. Este
programa (root, chamado pelo henbox-root.sh enquanto o PS2 está no cabo) escuta o eth0 e grava em pcap só os pacotes
entre o PS2 e endereços da INTERNET — o jogo online. Nada do que é da rede de casa (Samba do OPL, navegador, udpfs,
telemetria do OPL-RA) entra. Não altera nenhum pacote: só lê.

Uma partida = um arquivo: o primeiro pacote abre /data/local/henbox-rede/capturas/AAAAMMDD-HHMMSS.pcap e 10 min sem
tráfego fecham. Teto de 150 MB por arquivo e 600 MB no total (apaga os mais antigos). Em resumo.json: arquivo atual,
pacotes e os endereços remotos mais falados (o notebook usa para saber o que buscar).
Uso: captura-jogo.py <IP do PS2>
"""
import json, os, socket, struct, sys, time

PS2 = socket.inet_aton(sys.argv[1])
PASTA = '/data/local/henbox-rede/capturas'
OCIOSO = 600
MAX_ARQ, MAX_TOTAL = 150 << 20, 600 << 20
ETH_P_ALL = 0x0003


def local(ip):   # rede de casa / privada: fora da gravação
    a, b = ip[0], ip[1]
    return a == 10 or a == 127 or (a == 172 and 16 <= b < 32) or (a == 192 and b == 168) or a >= 224 or ip == b'\xff' * 4


def limpar():
    arqs = sorted(os.path.join(PASTA, n) for n in os.listdir(PASTA) if n.endswith('.pcap'))
    total = sum(os.path.getsize(a) for a in arqs)
    while arqs[:-1] and total > MAX_TOTAL:
        total -= os.path.getsize(arqs[0])
        os.remove(arqs.pop(0))


def main():
    os.makedirs(PASTA, exist_ok=True)
    os.chmod(PASTA, 0o755)
    so = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    so.bind(('eth0', 0))
    so.settimeout(5)
    f, nome, ultimo, pacotes, remotos, salvo = None, '', 0, 0, {}, 0
    while True:
        try:
            quadro, end = so.recvfrom(65535)
        except socket.timeout:
            quadro = None
        agora = time.time()
        if quadro and len(quadro) >= 34 and quadro[12:14] == b'\x08\x00':
            orig, dest = quadro[26:30], quadro[30:34]
            outro = dest if orig == PS2 else orig if dest == PS2 else None
            # no eth0 cada pacote passa uma vez: do PS2 entrando, para o PS2 saindo (a box repassa pelo Wi-Fi)
            if outro and not local(outro):
                if f is None or f.tell() > MAX_ARQ:
                    if f:
                        f.close()
                    nome = os.path.join(PASTA, time.strftime('%Y%m%d-%H%M%S') + '.pcap')
                    f = open(nome, 'wb')
                    f.write(struct.pack('<IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))   # pcap, Ethernet
                    pacotes, remotos = 0, {}
                    limpar()
                f.write(struct.pack('<IIII', int(agora), int(agora % 1 * 1e6), len(quadro), len(quadro)) + quadro)
                pacotes += 1
                ultimo = agora
                proto = quadro[23]
                ihl = (quadro[14] & 15) * 4
                porta = struct.unpack('>H', quadro[14 + ihl + (0 if orig != PS2 else 2):][:2])[0] if proto in (6, 17) else 0
                chave = f'{socket.inet_ntoa(outro)}:{porta}/{"tcp" if proto == 6 else "udp" if proto == 17 else proto}'
                remotos[chave] = remotos.get(chave, 0) + 1
        if f and agora - ultimo > OCIOSO:
            f.close()
            f = None
        if agora - salvo > 10:
            salvo = agora
            if f:
                f.flush()
            top = sorted(remotos.items(), key=lambda x: -x[1])[:15]
            with open(os.path.join(PASTA, 'resumo.json.tmp'), 'w') as r:
                json.dump({'gravando': bool(f), 'arquivo': os.path.basename(nome), 'pacotes': pacotes,
                           'ultimo': int(ultimo), 'remotos': top}, r)
            os.replace(os.path.join(PASTA, 'resumo.json.tmp'), os.path.join(PASTA, 'resumo.json'))
            os.chmod(os.path.join(PASTA, 'resumo.json'), 0o644)


if __name__ == '__main__':
    main()
