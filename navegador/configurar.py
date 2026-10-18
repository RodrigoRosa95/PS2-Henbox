#!/usr/bin/env python3
"""Configuração única do navegador do PS2 na TV box (pedido do usuário 17/10/2026: app instalador no celular, IP do
PS2 configurável, tela de estado). Fica em ~/ps2nav; config.json ao lado:
  {"ps2": {"ip": "192.168.4.230", "mascara": "255.255.255.0", "gw": "192.168.4.1"},
   "notebook": {"urls": ["http://192.168.4.135:8781", "https://ps2videos.rodrigoflix.com"], "chave": "...",
                "casa": "http://192.168.4.135:8770"}}

  configurar.py aplicar   gera remoto.json (servidor_host/videos/udpfs_nuvem), ps2/IPCONFIG.DAT (vai para o pendrive do
                          PS2 ao lado do navegador.elf) e o ip= das configs de rede do Neutrino (ps2/neutrino/config)
  configurar.py ip-ps2    só imprime o IP do PS2 (iniciar.sh)
  configurar.py estado    JSON com o estado da box para o app do celular
  configurar.py ip IP [MÁSCARA GW]   troca o IP do PS2 no config.json e aplica
  configurar.py ip-auto   (18/10/2026) se o IP do PS2 não é da rede do cabo da box (eth0), escolhe um livre nela
                          (.230, .231… sem resposta ao ping) com a máscara e o gateway da box; imprime "IP MÁSCARA GW"
  configurar.py servidor URL CHAVE   endereço do servidor em nuvem (porta 8781, http da rede local ou https) e a chave;
                          URL vazia = sem servidor (só o que está na box)
"""
import json, os, re, shutil, socket, subprocess, sys, time

PASTA = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(PASTA, 'config.json')
PADRAO = {'ps2': {'ip': '192.168.4.230', 'mascara': '255.255.255.0', 'gw': '192.168.4.1'},
          'notebook': {'urls': [], 'chave': '', 'casa': ''}}


def ler():
    try:
        c = json.load(open(CONFIG))
    except (OSError, ValueError):
        c = {}
    for k, v in PADRAO.items():
        c.setdefault(k, {})
        for k2, v2 in v.items():
            c[k].setdefault(k2, v2)
    return c


def gravar(caminho, texto, modo=0o644):
    tmp = caminho + '.tmp'
    with open(tmp, 'w') as f:
        f.write(texto)
    os.chmod(tmp, modo)
    os.replace(tmp, caminho)


def aplicar():
    c = ler()
    p, nb = c['ps2'], c['notebook']
    gravar(os.path.join(PASTA, 'remoto.json'), json.dumps(nb, ensure_ascii=False) + '\n', 0o600)
    gravar(os.path.join(PASTA, 'ps2', 'IPCONFIG.DAT'), f"{p['ip']} {p['mascara']} {p['gw']}\n")
    pasta_cfg = os.path.join(PASTA, 'ps2', 'neutrino', 'config')
    for nome in os.listdir(pasta_cfg) if os.path.isdir(pasta_cfg) else []:
        arq = os.path.join(pasta_cfg, nome)
        texto = open(arq).read()
        novo = re.sub(r'"ip=\d+\.\d+\.\d+\.\d+"', f'"ip={p["ip"]}"', texto)
        if novo != texto:
            gravar(arq, novo)
    return c


def rede_eth0():
    """(ip, prefixo, gateway) do cabo da box, ou None."""
    try:
        addr = subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'eth0'], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)', addr)
        if not m:
            return None
        rotas = ''
        for tab in ('eth0', 'main'):
            rotas += subprocess.run(['ip', 'route', 'show', 'table', tab], capture_output=True, text=True,
                                    timeout=5).stdout
        g = re.search(r'default via (\d+\.\d+\.\d+\.\d+) dev eth0', rotas)
        return m.group(1), int(m.group(2)), g.group(1) if g else ''
    except (OSError, subprocess.SubprocessError):
        return None


def ip_auto():
    import ipaddress
    c = ler()
    r = rede_eth0()
    if not r:
        return c['ps2']
    ip_box, prefixo, gw = r
    rede = ipaddress.ip_network(f'{ip_box}/{prefixo}', strict=False)
    if ipaddress.ip_address(c['ps2']['ip']) in rede:
        return c['ps2']
    base = int(rede.network_address)
    for fim in list(range(230, 254)) + list(range(200, 230)):
        cand = str(ipaddress.ip_address(base + fim))
        if ipaddress.ip_address(cand) not in rede or cand in (ip_box, gw):
            continue
        if subprocess.run(['ping', '-c', '1', '-W', '1', cand], capture_output=True).returncode != 0:
            c['ps2'] = {'ip': cand, 'mascara': str(rede.netmask), 'gw': gw or str(ipaddress.ip_address(base + 1))}
            gravar(CONFIG, json.dumps(c, ensure_ascii=False, indent=1) + '\n', 0o600)
            aplicar()
            break
    return c['ps2']


def servidor(url, chave):
    c = ler()
    # vários endereços separados por vírgula/espaço (ex.: o de casa e o https), tentados nessa ordem
    urls = [u.strip().rstrip('/') for u in re.split(r'[,\s]+', url) if u.strip()]
    m = next((re.match(r'^http://([^/:]+):8781$', u) for u in urls if re.match(r'^http://([^/:]+):8781$', u)), None)
    c['notebook'] = {'urls': urls, 'chave': chave.strip(),
                     'casa': f'http://{m.group(1)}:8770' if m else ''}
    gravar(CONFIG, json.dumps(c, ensure_ascii=False, indent=1) + '\n', 0o600)
    aplicar()


def porta_aberta(host, porta, t=1.0):
    try:
        with socket.create_connection((host, porta), timeout=t):
            return True
    except OSError:
        return False


def navegador(pedido):
    try:
        with socket.create_connection(('127.0.0.1', 8772), timeout=3) as s:
            s.sendall((pedido + '\n').encode())
            return s.makefile().readline().strip()
    except OSError:
        return ''


def ultima(arq, padrao=None):
    try:
        linhas = open(os.path.join(PASTA, arq), errors='replace').read().splitlines()
    except OSError:
        return ''
    if padrao:
        linhas = [l for l in linhas if padrao in l]
    return linhas[-1].strip() if linhas else ''


def processos():
    try:
        ps = '/system/bin/ps' if os.path.exists('/system/bin/ps') else 'ps'   # o ps do Termux não entende -o ARGS
        saida = subprocess.run([ps, '-A', '-o', 'ARGS'], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        saida = ''
    return {nome: nome in saida for nome in ('servidor_host.py', 'navegador_servidor.py', 'videos.py', 'udpfs_nuvem.py')}


def estado():
    c = ler()
    ip = c['ps2']['ip']
    ping = subprocess.run(['ping', '-c', '1', '-W', '1', ip], capture_output=True).returncode == 0
    host = ultima('host.log', 'PS2 conectado') or ''
    host_fim = ultima('host.log', 'conexão encerrada') or ''
    st = shutil.disk_usage(PASTA)
    nb = 'fora do alcance'
    for url in c['notebook'].get('urls', []):
        m = re.match(r'https?://([^/:]+)(?::(\d+))?', url)
        if m and porta_aberta(m.group(1), int(m.group(2) or (443 if url.startswith('https') else 80)), 3):
            nb = url
            break
    return {
        'hora': time.strftime('%d/%m %H:%M:%S'),
        'ps2': {'ip': ip, 'responde_ping': ping, 'navegador': navegador('status') or 'servidor parado',
                'ultima_conexao': host, 'ultima_queda': host_fim},
        'servicos': processos(),
        'webview': porta_aberta('127.0.0.1', 9222) and porta_aberta('127.0.0.1', 9223),
        'pagina': porta_aberta('127.0.0.1', 8780),
        'notebook': nb,
        'jogos': {'ultimo': ultima(os.path.join('..', 'udpfs.log'), 'OPEN') [-160:]},
        'espaco_livre_mb': st.free >> 20,
        'versao': open(os.path.join(PASTA, 'VERSAO')).read().strip() if os.path.exists(os.path.join(PASTA, 'VERSAO')) else '',
    }


if __name__ == '__main__':
    acao = sys.argv[1] if len(sys.argv) > 1 else 'estado'
    if acao == 'aplicar':
        aplicar()
        print('ok')
    elif acao == 'ip-ps2':
        print(ler()['ps2']['ip'])
    elif acao == 'ip-auto':
        p = ip_auto()
        print(p['ip'], p['mascara'], p['gw'])
    elif acao == 'servidor':
        servidor(sys.argv[2] if len(sys.argv) > 2 else '', sys.argv[3] if len(sys.argv) > 3 else '')
        print('ok')
    elif acao == 'ip':
        c = ler()
        c['ps2']['ip'] = sys.argv[2]
        if len(sys.argv) > 4:
            c['ps2']['mascara'], c['ps2']['gw'] = sys.argv[3], sys.argv[4]
        gravar(CONFIG, json.dumps(c, ensure_ascii=False, indent=1) + '\n', 0o600)
        aplicar()
        print('ok')
    else:
        print(json.dumps(estado(), ensure_ascii=False))
