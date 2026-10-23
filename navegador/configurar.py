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
        # os /32 com rótulo eth0:henbox são da ponte do henbox-root.sh (PS2 direto no cabo), não de um roteador
        m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)(?![^\n]*eth0:henbox)', addr)
        if not m or m.group(2) == '32':
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


REDE = '/data/local/henbox-rede'   # estado do henbox-root.sh (PS2 direto no cabo da box)


def ler_arq(caminho, padrao=''):
    try:
        return open(caminho).read().strip()
    except OSError:
        return padrao


def checklist():
    """Lista de conferência da instalação (23/10/2026), para a página /estado e o app do celular:
    [{"ok": true|false|null, "item": ..., "detalhe": ..., "resolver": ...}] — null = opcional/sem como saber."""
    e = estado()
    itens = []

    def add(ok, item, detalhe, resolver=''):
        itens.append({'ok': ok, 'item': item, 'detalhe': detalhe, 'resolver': '' if ok else resolver})

    parados = [k for k, v in e['servicos'].items() if not v]
    add(not parados, 'Servidores da TV box', 'todos no ar' if not parados else 'parados: ' + ', '.join(parados),
        'No app: Reiniciar serviços')
    add(e['webview'], 'Tela do PS2 (app PS2 Navegador)', 'pronta' if e['webview'] else 'o app da box não respondeu',
        'No app: Reiniciar serviços (abre o PS2 Navegador na TV)')
    boot = os.path.exists(os.path.expanduser('~/.termux/boot/ps2nav'))
    add(boot, 'Liga sozinho com a TV box', 'Termux:Boot + app PS2 Navegador' if boot else 'sem o script de início',
        'No app: Instalar / atualizar tudo')
    try:   # o laço root grava a hora a cada volta (o /proc de outro usuário não aparece para o Termux)
        vivo = time.time() - int(ler_arq(os.path.join(REDE, 'vivo'), '0')) < 30
    except ValueError:
        vivo = False
    modo = ler_arq(os.path.join(REDE, 'estado')).split()
    if modo:
        rede = (f'PS2 direto no cabo da box — {"mesma rede do Wi-Fi (ponte)" if modo[0] == "ponte" else "rede própria (NAT)"}'
                f', internet pelo Wi-Fi da box')
    else:
        rede = 'PS2 e TV box no roteador (ou cabo desligado)'
    add(vivo, 'Rede do PS2', rede if vivo else rede + ' — vigia do cabo parada (precisa de root)',
        'No app: Reiniciar serviços')
    ps2 = e['ps2']
    add(ps2['responde_ping'] or None, 'PS2 na rede', f"IP {ps2['ip']}"
        + (' respondendo' if ps2['responde_ping'] else ' sem resposta agora (normal com o PS2 desligado)'),
        'Abra o OPL → Apps → PS2 Henbox')
    pend = ultima('navegador.log', 'pendrive:') or ''
    add(None if not pend else 'diferente' not in pend and 'Não deu' not in pend and 'erro' not in pend,
        'Pendrive do PS2', pend.split('pendrive:', 1)[-1].strip() or 'ainda não conferido (abra o navegador no PS2)',
        'No app: Preparar pendrive (na USB da TV box)')
    jogos = os.path.realpath(os.path.join(PASTA, 'ps2', 'jogos-box'))
    n = len([a for a in os.listdir(jogos) if a.lower().endswith('.iso')]) if os.path.isdir(jogos) else 0
    add(n > 0 or None, 'Jogos na TV box', f'{n} ISO(s) em {jogos}' if n else 'nenhum pendrive/HD com a pasta DVD na box',
        'Opcional: pendrive/HD na USB da box com as pastas DVD/ e CD/')
    tem_srv = bool(ler()['notebook'].get('urls'))
    add((e['notebook'] != 'fora do alcance') if tem_srv else None, 'Servidor em nuvem',
        e['notebook'] if tem_srv else 'não configurado (opcional)', 'Confira se o PC do servidor está ligado')
    udp = ler_arq('/proc/net/udp') + ler_arq('/proc/net/udp6')
    xera = ':4712 ' in udp
    add(xera or None, 'Conquistas (xeRAbora)', 'motor no ar' if xera else 'não instalado ou parado (opcional)',
        'No app: Instalar conquistas')
    add(e['espaco_livre_mb'] > 300, 'Espaço livre na box', f"{e['espaco_livre_mb']} MB", 'Apague apps ou arquivos da box')
    atu = ultima('atualizar.log', '') or ''
    add(None if not atu else 'erro' not in atu.lower(), 'Versão', (e['versao'] or '?') + (' — ' + atu if atu else ''),
        'Atualize pelo app: Instalar / atualizar tudo')
    return itens


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
    elif acao == 'checklist':
        print(json.dumps(checklist(), ensure_ascii=False))
    else:
        print(json.dumps(estado(), ensure_ascii=False))
