#!/usr/bin/env python3
"""Central do celular na TV box (pedido do usuário 24/10/2026) — porta 8785, página /celular (aberta pelo app PS2 Henbox
ou por qualquer navegador na rede de casa).

  🖼 Capas      ISOs do pendrive da box (DVD/, CD/) identificados pelo código do jogo (nome do arquivo ou SYSTEM.CNF);
               capa do xlenore/ps2-covers (o acervo que o PCSX2 usa), reduzida para 140x200 e gravada como
               ART/<código>_COV.jpg, o nome que o OPL procura (o mesmo que o OPL Manager do PC grava)
  📁 Arquivos   pendrive da box (gravação como root) e, com o navegador aberto no PS2, mc0:/ mc1:/ mass:/ pelas ops do
               navegador.elf (0 copiar, 3 apagar, 5 listar, 6 criar pasta, 7 apagar pasta); pastas do sistema protegidas
  🖱 Controle   touchpad e teclado do celular → navegador_servidor.py ("remoto"): Loja, sistema e qualquer página
  📱 Celular    ISOs da memória do celular (o app serve por HTTP com Range e se registra aqui): jogar direto (Neutrino
               pelo udpfs_nuvem.py), copiar para o pendrive da box ou para o pendrive do PS2 (host:celular/...)
  🌐 Kits       kits online da comunidade (kits_servidor.py): VMC + CFG + patch PPF + DNS, nunca o ISO. Confere a
               versão do ISO pelo hash do RetroAchievements (ra_hash.py) e aplica no pendrive da box

Gravação no pendrive: o Termux só lê /storage/XXXX; grava como root em /mnt/media_rw/XXXX (su -c cat).
Teste no notebook: CENTRAL_PENDRIVE=<pasta> (lê e grava ali, sem su).
Uso: central.py [porta]        central.py ppf-aplicar|ppf-desfazer <iso> <ppf|desfazer.json> [desfazer.json] (root)
"""
import base64, hashlib, json, os, re, shlex, socket, struct, subprocess, sys, threading, time, urllib.error
import urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8785
PASTA_PS2 = os.path.join(PASTA, 'ps2')
ARQUIVOS = os.path.join(PASTA_PS2, 'arquivos')          # host:arquivos/ — trocas com o PS2 (listas, cópias)
CAPAS = os.path.join(PASTA, 'capas')                     # capas já reduzidas (também para os ISOs do celular)
KITS_DIR = os.path.join(PASTA, 'kits')                   # kits baixados e o "desfazer" dos patches
CELULAR = os.path.join(PASTA, 'celular.json')            # lido também pelo udpfs_nuvem.py
DNS_KIT = os.path.join(PASTA, 'dns-kit.json')            # lido pelo videos.py (janela_dns) → henbox-root.sh
IDS = os.path.join(PASTA, 'central-ids.json')            # código e hash RA de cada ISO (nome|tamanho|data)
TESTE = os.environ.get('CENTRAL_PENDRIVE')
UA = 'ps2nav/1.0'
CAPAS_URL = 'https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/default/{}.jpg'
CAPA_TAM = (140, 200)                                    # tamanho recomendado do OPL para _COV
CODIGO = re.compile(r'([A-Z]{4})[_-](\d{3})\.?(\d{2})')
PS2_CAMINHO = re.compile(r'^(mc0|mc1|mass):/')
# não apagar nem sobrescrever pelo celular: boot do console, exploit, OPL, PS2Link e o próprio navegador
PROTEGIDOS = re.compile(r'^(mc[01]:/(BOOT|SYS-CONF|FORTUNA|OPL|APPS/PS2LINK|B[A-Z]?(EXEC|DATA)-SYSTEM)|[^/]*henbox'
                        r'|mass:/APPS/NAVEGADOR)(/|$)', re.I)
BOX_PROTEGIDOS = re.compile(r'^(APPS/NAVEGADOR|Android|LOST\.DIR)(/|$)', re.I)   # no pendrive da box
DNS_HORAS = 6                                            # o DNS do kit vale por 6 h depois de aplicado


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


class Erro(Exception):
    pass


def ler_json(caminho, padrao):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def gravar_json(caminho, obj):
    tmp = caminho + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def config():
    return ler_json(os.path.join(PASTA, 'config.json'), {})


# ---------------- pendrive da box ----------------
def pendrive():
    """(leitura, gravação) do pendrive de jogos da box: /storage/XXXX e /mnt/media_rw/XXXX (root); None sem pendrive."""
    if TESTE:
        return (TESTE, TESTE) if os.path.isdir(TESTE) else None
    alvo = os.path.realpath(os.path.join(PASTA_PS2, 'jogos-box'))
    raiz = os.path.dirname(alvo) if os.path.isdir(alvo) else None
    if not raiz:
        try:
            raiz = next((os.path.join('/storage', d) for d in sorted(os.listdir('/storage'))
                         if '-' in d and os.path.isdir(os.path.join('/storage', d, 'DVD'))), None)
        except OSError:
            raiz = None
    if not raiz:
        return None
    grav = os.path.join('/mnt/media_rw', os.path.basename(raiz))
    return raiz, grav


def relativo_seguro(rel):
    """Caminho dentro do pendrive ('DVD/x.iso'); recusa sair dele."""
    rel = os.path.normpath('/' + (rel or '').replace('\\', '/')).lstrip('/')
    if rel.startswith('..') or '\0' in rel:
        raise Erro('caminho inválido')
    return '' if rel == '.' else rel


def root(cmd, entrada=None, timeout=300):
    r = subprocess.run(['sh', '-c', cmd] if TESTE else ['su', '-c', cmd], input=entrada, capture_output=True,
                       timeout=timeout)
    if r.returncode:
        raise Erro((r.stderr or b'').decode(errors='replace').strip() or f'comando falhou ({r.returncode})')
    return r.stdout.decode(errors='replace')


class GravarRoot:
    """Arquivo aberto para gravação como root (o pendrive USB não aceita o usuário do Termux)."""

    def __init__(self, caminho, juntar=False):
        cmd = f'cat {">>" if juntar else ">"} {shlex.quote(caminho)}'
        self.p = subprocess.Popen(['sh', '-c', cmd] if TESTE else ['su', '-c', cmd], stdin=subprocess.PIPE,
                                  stderr=subprocess.PIPE)

    def write(self, d):
        self.p.stdin.write(d)

    def close(self):
        self.p.stdin.close()
        err = self.p.stderr.read()
        if self.p.wait():
            raise Erro(err.decode(errors='replace').strip() or 'erro gravando no pendrive')

    def __enter__(self):
        return self

    def __exit__(self, tipo, *_):
        if tipo:
            self.p.kill()
            self.p.wait()
        else:
            self.close()


def gravar_no_pendrive(rel, dados):
    pd = pendrive()
    if not pd:
        raise Erro('sem pendrive na box')
    destino = os.path.join(pd[1], relativo_seguro(rel))
    root(f'mkdir -p {shlex.quote(os.path.dirname(destino))}')
    with GravarRoot(destino) as g:
        g.write(dados)


def livre_pendrive():
    pd = pendrive()
    if not pd:
        return 0
    st = os.statvfs(pd[0])
    return st.f_bavail * st.f_frsize


# ---------------- jogos e capas ----------------
_ids_trava = threading.Lock()


def codigo_do_nome(nome):
    m = CODIGO.match(os.path.basename(nome).upper())
    return f'{m.group(1)}_{m.group(2)}.{m.group(3)}' if m else None


def codigo_do_iso(f):
    """Código do jogo pelo BOOT2 do SYSTEM.CNF (f = arquivo aberto com read/seek)."""
    import ra_hash
    cnf = ra_hash.achar(f, 'SYSTEM.CNF')
    if not cnf:
        return None
    texto = ra_hash._ler(f, cnf[0], min(cnf[1], 2047)).decode('latin-1').upper()
    m = CODIGO.search(texto)
    return f'{m.group(1)}_{m.group(2)}.{m.group(3)}' if m else None


def info_iso(caminho):
    """{"codigo", "ra"} de um ISO do pendrive, guardado em central-ids.json (o hash RA só quando pedido)."""
    st = os.stat(caminho)
    chave = f'{os.path.basename(caminho)}|{st.st_size}|{int(st.st_mtime)}'
    with _ids_trava:
        ids = ler_json(IDS, {})
        if chave in ids:
            return ids[chave]
    info = {'codigo': codigo_do_nome(caminho)}
    if caminho.lower().endswith('.iso'):
        try:
            with open(caminho, 'rb') as f:
                info['codigo'] = codigo_do_iso(f) or info['codigo']
        except (OSError, ValueError, struct.error) as e:
            log('código:', caminho, e)
    with _ids_trava:
        ids = ler_json(IDS, {})
        ids[chave] = info
        gravar_json(IDS, ids)
    return info


def hash_ra(caminho):
    """Hash do RetroAchievements do ISO (MD5 do executável de boot): identifica a versão exata do jogo."""
    st = os.stat(caminho)
    chave = f'{os.path.basename(caminho)}|{st.st_size}|{int(st.st_mtime)}'
    info = info_iso(caminho)
    if info.get('ra'):
        return info['ra']
    import ra_hash
    try:
        h = ra_hash.hash_ps2(caminho)[0]
    except (OSError, ValueError, struct.error):
        h = ''
    with _ids_trava:
        ids = ler_json(IDS, {})
        ids.setdefault(chave, info)['ra'] = h
        gravar_json(IDS, ids)
    return h


def tem_capa(arte, codigo):
    return any(f'{codigo}_COV.{e}'.upper() in arte for e in ('jpg', 'png'))


def jogos_box():
    pd = pendrive()
    if not pd:
        return []
    try:
        arte = {n.upper() for n in os.listdir(os.path.join(pd[0], 'ART'))}
    except OSError:
        arte = set()
    jogos = []
    for pasta in ('DVD', 'CD'):
        try:
            nomes = sorted(os.listdir(os.path.join(pd[0], pasta)), key=str.lower)
        except OSError:
            continue
        for nome in nomes:
            if not nome.lower().endswith(('.iso', '.zso', '.cso')):
                continue
            cam = os.path.join(pd[0], pasta, nome)
            try:
                info, tam = info_iso(cam), os.path.getsize(cam)
            except OSError:
                continue
            cod = info.get('codigo')
            jogos.append({'onde': 'box', 'pasta': pasta, 'nome': nome, 'tam': tam, 'codigo': cod,
                          'titulo': titulo_do_nome(nome), 'capa': bool(cod and tem_capa(arte, cod))})
    return jogos


def titulo_do_nome(nome):
    t = os.path.splitext(nome)[0]
    m = CODIGO.match(t.upper())
    if m:
        t = t[m.end():].lstrip(' ._-')
    return t or nome


def baixar_capa(codigo):
    """Capa reduzida (bytes JPEG) do cache ou do xlenore/ps2-covers; None se o acervo não tem."""
    os.makedirs(CAPAS, exist_ok=True)
    local = os.path.join(CAPAS, codigo + '.jpg')
    if os.path.exists(local):
        return open(local, 'rb').read()
    falta = os.path.join(CAPAS, codigo + '.sem')
    if os.path.exists(falta) and time.time() - os.path.getmtime(falta) < 7 * 86400:
        return None
    url = CAPAS_URL.format(codigo.replace('_', '-').replace('.', ''))
    try:
        d = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            open(falta, 'w').close()
            return None
        raise
    from PIL import Image
    img = Image.open(BytesIO(d)).convert('RGB').resize(CAPA_TAM, Image.LANCZOS)
    saida = BytesIO()
    img.save(saida, 'JPEG', quality=88)
    with open(local + '.tmp', 'wb') as f:
        f.write(saida.getvalue())
    os.replace(local + '.tmp', local)
    return saida.getvalue()


def capas_para_box(t, codigos=None):
    """Tarefa: baixa e grava no ART/ do pendrive as capas que faltam (ou as dos códigos pedidos)."""
    jogos = [j for j in jogos_box() if j['codigo'] and (codigos is None or j['codigo'] in codigos)]
    faltam = sorted({j['codigo'] for j in jogos if codigos is not None or not j['capa']})
    novas, sem = 0, []
    for k, cod in enumerate(faltam):
        t['msg'] = f'{cod} ({k + 1} de {len(faltam)})'
        t['pct'] = k * 100 // max(1, len(faltam))
        try:
            d = baixar_capa(cod)
        except Exception as e:
            sem.append(f'{cod} (erro: {e})')
            continue
        if d is None:
            sem.append(cod)
            continue
        gravar_no_pendrive(f'ART/{cod}_COV.jpg', d)
        novas += 1
    t['msg'] = f'{novas} capa(s) nova(s)' + (f'; sem capa no acervo: {", ".join(sem)}' if sem else '') \
        if faltam else 'todas as capas já estavam no pendrive'


# ---------------- tarefas em segundo plano ----------------
TAREFAS, _tarefa_n = {}, [0]


def tarefa(titulo, func, *args):
    _tarefa_n[0] += 1
    t = {'id': _tarefa_n[0], 'titulo': titulo, 'estado': 'rodando', 'pct': 0, 'msg': '', 'inicio': time.time()}
    TAREFAS[t['id']] = t

    def rodar():
        try:
            func(t, *args)
            t['estado'], t['pct'] = 'pronto', 100
        except Exception as e:
            t['estado'], t['msg'] = 'erro', str(e)
            log('tarefa', titulo, 'falhou:', e)
        t['fim'] = time.time()
    threading.Thread(target=rodar, daemon=True).start()
    for v in [v for v in TAREFAS.values() if v.get('fim', time.time()) < time.time() - 3600]:
        TAREFAS.pop(v['id'], None)   # guarda só a última hora
    return t


# ---------------- PS2 (pelo navegador aberto) ----------------
_rotulo_n = [int(time.time()) % 100000]


def nav(pedido, timeout=8):
    try:
        with socket.create_connection(('127.0.0.1', 8772), timeout=timeout) as c:
            c.sendall((pedido + '\n').encode())
            return c.makefile(encoding='utf-8', errors='replace').readline().strip()
    except OSError as e:
        return f'navegador fora do ar ({e})'


def ps2_aberto():
    return nav('status', 3) == 'aberto'


def caminho_ps2(c, gravar=False):
    c = (c or '').strip().replace('\\', '/')
    if not PS2_CAMINHO.match(c) or '/../' in c + '/' or '|' in c or len(c.encode()) > 127:
        raise Erro('caminho do PS2 inválido (mc0:/, mc1:/ ou mass:/, até 127 letras)')
    if gravar and PROTEGIDOS.match(c):
        raise Erro('pasta protegida (sistema, exploit, OPL ou navegador): não mexo pelo celular')
    return c


def ps2_op(op, origem, destino='-', tam=0, espera=60, t=None):
    """Pede uma operação ao navegador.elf e espera o resultado (resultados[rótulo] do navegador_servidor)."""
    _rotulo_n[0] += 1
    rot = f'__central{_rotulo_n[0]}__'
    r = nav(f'op {op}|{origem}|{destino}|{rot}|{tam}')
    if r != 'ok':
        raise Erro(r)
    fim = time.time() + espera
    while time.time() < fim:
        time.sleep(0.4)
        try:
            st = json.loads(nav('pedido'))
        except ValueError:
            continue
        res = st.get('resultados', {}).get(rot)
        if res:
            if not res.get('ok'):
                raise Erro(f'PS2: {res.get("estado")}')
            return
        atual = st.get('atual') or {}
        if t is not None and atual.get('arquivo') == rot:
            t['pct'] = atual.get('pct') or 0
    raise Erro('o PS2 não respondeu a tempo (o navegador continua aberto?)')


def ps2_listar(c):
    c = caminho_ps2(c)
    os.makedirs(ARQUIVOS, exist_ok=True)
    _rotulo_n[0] += 1
    nome = f'lista-{_rotulo_n[0]}.txt'
    ps2_op(5, c, f'host:arquivos/{nome}', espera=30)
    arq = os.path.join(ARQUIVOS, nome)
    try:
        linhas = open(arq, encoding='latin-1').read().splitlines()
    finally:
        try:
            os.remove(arq)
        except OSError:
            pass
    itens = []
    for l in linhas:
        partes = l.split('\t')
        if len(partes) == 3:
            itens.append({'nome': partes[1], 'pasta': partes[0] == 'D', 'tam': int(partes[2] or 0),
                          'protegido': bool(PROTEGIDOS.match(c.rstrip('/') + '/' + partes[1]))})
    return sorted(itens, key=lambda i: (not i['pasta'], i['nome'].lower()))


# ---------------- celular ----------------
def celular():
    return ler_json(CELULAR, {})


def celular_pedir(caminho, timeout=15, cabecalhos=None):
    c = celular()
    if not c.get('url'):
        raise Erro('nenhum celular registrado (abra a Central pelo app PS2 Henbox)')
    req = urllib.request.Request(c['url'].rstrip('/') + caminho,
                                 headers={'X-Chave': c.get('chave', ''), **(cabecalhos or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def celular_registrar(url, chave):
    if not re.match(r'^http://[\w.\-:\[\]]+$', url or ''):
        raise Erro('endereço do celular inválido')
    req = urllib.request.Request(url.rstrip('/') + '/lista', headers={'X-Chave': chave or ''})
    lista = json.load(urllib.request.urlopen(req, timeout=20))
    isos = []
    for x in lista.get('isos', []):
        nome = os.path.basename(str(x.get('nome', '')))
        if nome.lower().endswith('.iso') and '|' not in nome and len(nome.encode()) <= 100:
            isos.append({'i': int(x['i']), 'nome': nome, 'tam': int(x.get('tam', 0)),
                         'pasta': 'CD' if x.get('pasta') == 'CD' else 'DVD',
                         'codigo': x.get('codigo') or codigo_do_nome(nome), 'caminho': x.get('caminho', '')})
    dados = {'url': url.rstrip('/'), 'chave': chave or '', 'aparelho': lista.get('aparelho', 'celular'),
             'isos': isos, 'quando': time.time()}
    gravar_json(CELULAR, dados)
    log(f'celular registrado: {dados["aparelho"]} {url} com {len(isos)} ISO(s)')
    return dados


def iso_do_celular(nome):
    iso = next((x for x in celular().get('isos', []) if x['nome'] == nome), None)
    if not iso:
        raise Erro('esse ISO não está na lista do celular (atualize a lista no app)')
    return iso


def celular_para_box(t, nome):
    """Copia o ISO do celular para DVD/ (ou CD/) do pendrive da box, continuando de onde parou."""
    iso = iso_do_celular(nome)
    pd = pendrive()
    if not pd:
        raise Erro('sem pendrive na box')
    rel = f'{iso["pasta"]}/{nome}'
    if os.path.exists(os.path.join(pd[0], rel)):
        t['msg'] = 'já estava no pendrive da box'
        return
    parcial_l, parcial_g = os.path.join(pd[0], rel + '.parcial'), os.path.join(pd[1], rel + '.parcial')
    feito = os.path.getsize(parcial_l) if os.path.exists(parcial_l) else 0
    if iso['tam'] - feito > livre_pendrive() - (64 << 20):
        raise Erro(f'falta espaço no pendrive da box: precisa de {(iso["tam"] - feito) >> 20} MB, '
                   f'tem {livre_pendrive() >> 20} MB livres')
    root(f'mkdir -p {shlex.quote(os.path.dirname(parcial_g))}')
    inicio = time.time()
    with GravarRoot(parcial_g, juntar=feito > 0) as g:
        r = celular_pedir(f'/iso/{iso["i"]}/{urllib.parse.quote(nome)}', timeout=60,
                          cabecalhos={'Range': f'bytes={feito}-'} if feito else None)
        if feito and r.status != 206:
            raise Erro('o celular não continuou a cópia (sem Range)')
        while True:
            d = r.read(1 << 20)
            if not d:
                break
            g.write(d)
            feito += len(d)
            t['pct'] = feito * 100 // max(1, iso['tam'])
            vel = feito / max(1, time.time() - inicio) / (1 << 20)
            t['msg'] = f'{feito >> 20} de {iso["tam"] >> 20} MB · {vel:.1f} MB/s'
    if feito != iso['tam']:
        raise Erro(f'a cópia parou em {feito >> 20} MB (toque de novo para continuar)')
    root(f'mv {shlex.quote(parcial_g)} {shlex.quote(os.path.join(pd[1], rel))}')
    t['msg'] = f'✔ {nome} no pendrive da box'


# ---------------- kits online ----------------
def kits_urls():
    c = config()
    if c.get('kits'):
        return c['kits'] if isinstance(c['kits'], list) else [c['kits']]
    casa = (c.get('notebook') or {}).get('casa') or ''
    host = urllib.parse.urlparse(casa).hostname
    return [f'http://{host}:8792'] if host else []


def notebook_pedir(caminho, dados=None, timeout=30):
    """O catálogo de GAMES ONLINE (aba 🌐 da loja) e a instalação por 1 clique vivem no notebook
    (servidor.py 8770). A central (8785) faz a ponte para o app instalador da TV box (28/10/2026).
    Na box de convidado (instalada do zero, modo nuvem) o catálogo vem do https do autor com a chave do
    convidado; aí o caminho ganha o prefixo /loja e não existe instalação local (o jogo roda direto)."""
    c = config()
    nb = c.get('notebook') or {}
    casa = (nb.get('casa') or '').rstrip('/')
    chave = nb.get('chave', '')
    if not casa:
        urls = nb.get('urls') or []
        if not urls:
            raise Erro('sem servidor do catálogo na configuração (conecte pelo app PS2 Henbox)')
        casa = urls[0].rstrip('/')
        if not caminho.startswith('/loja'):
            caminho = '/loja' + caminho
    cab = {'User-Agent': UA, 'X-Chave': chave}
    if dados is None:
        req = urllib.request.Request(casa + caminho, headers=cab)
    else:
        req = urllib.request.Request(casa + caminho, data=json.dumps(dados).encode(),
                                     headers={'Content-Type': 'application/json', **cab})
    return urllib.request.urlopen(req, timeout=timeout)


def notebook_nuvem():
    return not ((config().get('notebook') or {}).get('casa', '').strip())


def kits_pedir(caminho, dados=None, timeout=30):
    ultimo = None
    for url in kits_urls():
        try:
            req = urllib.request.Request(url.rstrip('/') + caminho, data=dados,
                                         headers={'User-Agent': UA, 'Content-Type': 'application/json'})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            raise Erro(e.read().decode(errors='replace')[:300] or f'HTTP {e.code}')
        except OSError as e:
            ultimo = e
    raise Erro(f'servidor de kits fora do alcance ({ultimo})' if kits_urls() else 'nenhum servidor de kits configurado')


def kits_catalogo():
    return json.loads(kits_pedir('/kits/catalogo.json')).get('kits', [])


def kits_com_jogos():
    """Catálogo + quais ISOs da box e do celular servem para cada kit (pelo código; versão pelo hash RA)."""
    kits = kits_catalogo()
    pd = pendrive()
    meus = jogos_box() + [{'onde': 'celular', **x, 'titulo': titulo_do_nome(x['nome'])} for x in celular().get('isos', [])]
    for k in kits:
        hashes = {v.get('ra_hash') for v in k.get('versoes', []) if v.get('ra_hash')}
        k['meus'] = []
        for j in meus:
            if j.get('codigo') != k.get('codigo'):
                continue
            item = {'onde': j['onde'], 'nome': j['nome'], 'pasta': j.get('pasta', 'DVD')}
            if hashes and j['onde'] == 'box' and pd and j['nome'].lower().endswith('.iso'):
                item['compativel'] = hash_ra(os.path.join(pd[0], j['pasta'], j['nome'])) in hashes
            k['meus'].append(item)
    return kits


def cfg_mesclar(antigo, novo):
    """CFG do OPL (linhas chave=valor): as chaves do kit por cima das que já existiam."""
    def ler(t):
        d = {}
        for l in t.splitlines():
            if '=' in l:
                a, _, b = l.partition('=')
                d[a.strip()] = b.strip()
        return d
    d = ler(antigo)
    d.update(ler(novo))
    return ''.join(f'{a}={b}\r\n' for a, b in d.items())


def aplicar_kit(t, kit_id, onde, nome, forcar=False):
    kit = next((k for k in kits_catalogo() if k.get('id') == kit_id), None)
    if not kit:
        raise Erro('kit não encontrado no servidor')
    pd = pendrive()
    if not pd:
        raise Erro('sem pendrive na box (o kit vai para o pendrive que você leva ao PS2)')
    cod = kit['codigo']
    iso_local = None
    if onde == 'box':
        iso_local = next((os.path.join(pd[0], p, nome) for p in ('DVD', 'CD')
                          if os.path.exists(os.path.join(pd[0], p, nome))), None)
        if not iso_local:
            raise Erro('ISO não encontrado no pendrive da box')
    hashes = {v.get('ra_hash') for v in kit.get('versoes', []) if v.get('ra_hash')}
    if hashes and iso_local and not forcar:
        t['msg'] = 'conferindo a versão do jogo…'
        if hash_ra(iso_local) not in hashes:
            raise Erro('a versão do seu ISO é diferente da testada no kit (' + ', '.join(
                v.get('nome', '?') for v in kit.get('versoes', [])) + '). Use "aplicar mesmo assim" se quiser tentar')
    feitos = []
    pasta_kit = os.path.join(KITS_DIR, re.sub(r'[^\w.-]', '_', kit_id))
    os.makedirs(pasta_kit, exist_ok=True)
    arqs = kit.get('arquivos', [])
    for k, a in enumerate(arqs):
        t['msg'] = f'baixando {a["nome"]}'
        t['pct'] = k * 80 // max(1, len(arqs))
        d = kits_pedir(f'/kits/{urllib.parse.quote(kit_id)}/{urllib.parse.quote(a["nome"])}', timeout=120)
        if a.get('sha256') and hashlib.sha256(d).hexdigest() != a['sha256']:
            raise Erro(f'{a["nome"]} chegou diferente do catálogo (sha256)')
        tipo = a.get('tipo')
        if tipo == 'vmc':
            vmc = os.path.basename(kit.get('vmc_nome') or a['nome'])
            atual = os.path.join(pd[0], 'VMC', vmc)
            if os.path.exists(atual):
                if hashlib.sha256(open(atual, 'rb').read()).hexdigest() == hashlib.sha256(d).hexdigest():
                    feitos.append(f'VMC {vmc} já estava igual')
                    continue
                guarda = f'{vmc}.antes-kit-{time.strftime("%Y%m%d-%H%M")}'
                root(f'mv {shlex.quote(os.path.join(pd[1], "VMC", vmc))} {shlex.quote(os.path.join(pd[1], "VMC", guarda))}')
                feitos.append(f'VMC antigo guardado como {guarda}')
            gravar_no_pendrive(f'VMC/{vmc}', d)
            feitos.append(f'VMC/{vmc}')
        elif tipo == 'cfg':
            atual = os.path.join(pd[0], 'CFG', f'{cod}.cfg')
            antigo = open(atual, encoding='latin-1').read() if os.path.exists(atual) else ''
            gravar_no_pendrive(f'CFG/{cod}.cfg', cfg_mesclar(antigo, d.decode('latin-1')).encode('latin-1'))
            feitos.append(f'CFG/{cod}.cfg')
        elif tipo == 'ppf':
            if not iso_local:
                raise Erro('esse kit tem patch: copie o ISO do celular para o pendrive da box primeiro')
            ppf = os.path.join(pasta_kit, a['nome'])
            with open(ppf, 'wb') as f:
                f.write(d)
            desfazer = os.path.join(pasta_kit, f'desfazer-{os.path.basename(iso_local)}.json')
            if os.path.exists(desfazer):
                feitos.append('patch já estava aplicado neste ISO')
                continue
            t['msg'] = 'aplicando o patch no ISO…'
            iso_g = os.path.join(pd[1], os.path.relpath(iso_local, pd[0]))
            root(f'{shlex.quote(sys.executable)} {shlex.quote(os.path.abspath(__file__))} ppf-aplicar '
                 f'{shlex.quote(iso_g)} {shlex.quote(ppf)} {shlex.quote(desfazer)}', timeout=1800)
            feitos.append(f'patch {a["nome"]} aplicado (dá para desfazer)')
        elif tipo == 'capa':
            gravar_no_pendrive(f'ART/{cod}_COV.jpg', d)
            feitos.append('capa')
    if not any(a.get('tipo') == 'capa' for a in arqs):
        try:
            d = baixar_capa(cod)
            if d:
                gravar_no_pendrive(f'ART/{cod}_COV.jpg', d)
        except Exception as e:
            log('capa do kit:', e)
    if kit.get('dns'):
        gravar_json(DNS_KIT, {'ip': kit['dns'], 'ate': time.time() + DNS_HORAS * 3600, 'kit': kit_id})
        feitos.append(f'DNS {kit["dns"]} no PS2 pelo cabo da box por {DNS_HORAS} h')
    t['msg'] = '✔ ' + '; '.join(feitos) + '. Tire o pendrive, ponha no PS2 e abra o jogo pelo OPL.'


def enviar_kit(dados):
    """Kit da comunidade → servidor de kits (que confere e deixa para aprovação). "iso": nome de um ISO do pendrive
    da box, cuja versão (hash RA) vai junto como a testada."""
    iso = os.path.basename(dados.pop('iso', '') or '')
    pd = pendrive()
    if iso and pd:
        cam = next((os.path.join(pd[0], p, iso) for p in ('DVD', 'CD') if os.path.exists(os.path.join(pd[0], p, iso))), None)
        if cam:
            h = hash_ra(cam)
            if h:
                dados['versoes'] = [{'ra_hash': h, 'nome': titulo_do_nome(iso)}]
    for a in dados.get('arquivos', []):
        bruto = base64.b64decode(a.get('dados', ''), validate=True)
        if len(bruto) > 0x8006 and bruto[0x8001:0x8006] == b'CD001':
            raise Erro(f'{a.get("nome")}: é um ISO — a central só aceita VMC, CFG, patch e imagens')
    return json.loads(kits_pedir('/kits/enviar', json.dumps(dados).encode(), timeout=300))


# ---------------- PPF (rodado como root: central.py ppf-aplicar) ----------------
def ppf_registros(d):
    """(posição, bytes novos, bytes antigos ou None) de um patch PPF 1.0, 2.0 ou 3.0."""
    v = d[:5]
    if v == b'PPF10':
        p, larg, undo = 56, 4, False
    elif v == b'PPF20':
        p, larg, undo = 56 + 4 + 1024, 4, False
    elif v == b'PPF30':
        bloco, undo = d[57], bool(d[58])
        p, larg = 60 + (1024 if bloco else 0), 8
    else:
        raise Erro('não é um patch PPF')
    fim = len(d)
    diz = d.rfind(b'@BEGIN_FILE_ID.DIZ')
    if diz > 0:
        fim = diz
    while p < fim:
        pos = int.from_bytes(d[p:p + larg], 'little')
        n = d[p + larg]
        novo = d[p + larg + 1:p + larg + 1 + n]
        p += larg + 1 + n
        antigo = None
        if undo:
            antigo = d[p:p + n]
            p += n
        if len(novo) != n:
            break
        yield pos, novo, antigo


def ppf_aplicar(iso, ppf, desfazer):
    regs = list(ppf_registros(open(ppf, 'rb').read()))
    guardado = []
    with open(iso, 'r+b') as f:
        for pos, novo, _ in regs:
            f.seek(pos)
            guardado.append([pos, base64.b64encode(f.read(len(novo))).decode()])
        with open(desfazer, 'w') as g:   # antes de mexer: se cair no meio, dá para voltar
            json.dump({'iso': iso, 'trechos': guardado}, g)
        for pos, novo, _ in regs:
            f.seek(pos)
            f.write(novo)
    os.chmod(desfazer, 0o666)


def ppf_desfazer(iso, desfazer):
    dados = json.load(open(desfazer))
    with open(iso, 'r+b') as f:
        for pos, d in dados['trechos']:
            f.seek(pos)
            f.write(base64.b64decode(d))
    os.remove(desfazer)


# ---------------- HTTP ----------------
class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def responder(self, d, tipo='application/json', codigo=200, extra=None):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(d)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        for a, b in (extra or {}).items():
            self.send_header(a, b)
        self.end_headers()
        self.wfile.write(d)

    def json(self, obj, codigo=200):
        self.responder(json.dumps(obj, ensure_ascii=False).encode(), codigo=codigo)

    def corpo_json(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 150 << 20:
            raise Erro('envio grande demais')
        return json.loads(self.rfile.read(n) or b'{}')

    def chave_ok(self):
        chave = config().get('central_chave')
        if not chave:
            return True
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return self.headers.get('X-Chave') == chave or q.get('chave', [''])[0] == chave

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Chave')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {a: b[0] for a, b in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path in ('/', '/celular'):
                # central-compat.html (central_compat.js): a mesma página em ES5, para o WebView do Android 4.4 (Xoom)
                pag = next(p for p in ('central-compat.html', 'central.html') if os.path.exists(os.path.join(PASTA, p)))
                return self.responder(open(os.path.join(PASTA, pag), 'rb').read(), 'text/html; charset=utf-8')
            if u.path == '/henbox':
                return self.json({'app': 'ps2-henbox-central', 'porta': PORTA})
            if not self.chave_ok():
                return self.json({'erro': 'chave da central errada'}, 403)
            if u.path == '/api/estado':
                pd = pendrive()
                cel = celular()
                return self.json({'pendrive': pd[0] if pd else None, 'livre': livre_pendrive(),
                                  'ps2_aberto': ps2_aberto(), 'celular': {k: cel.get(k) for k in ('url', 'aparelho', 'quando')},
                                  'kits': kits_urls(), 'dns_kit': ler_json(DNS_KIT, {})})
            if u.path == '/api/jogos':
                cel = [{'onde': 'celular', **x, 'titulo': titulo_do_nome(x['nome'])} for x in celular().get('isos', [])]
                return self.json({'box': jogos_box(), 'celular': cel})
            if u.path in ('/api/online', '/api/online/fila'):   # 🌐 Games Online (catálogo vem do notebook)
                try:
                    dados = json.loads(notebook_pedir('/api/loja' if u.path.endswith('/fila') else '/api/online').read())
                except urllib.error.HTTPError as e:
                    return self.json({'erro': e.read().decode(errors='replace')[:200] or f'HTTP {e.code}'}, 502)
                except (OSError, ValueError) as e:
                    return self.json({'erro': f'notebook fora do ar: {e}'}, 502)
                except Erro as e:
                    return self.json({'erro': str(e)}, 503)
                if u.path.endswith('/fila'):
                    return self.json({'livre': dados.get('livre', 0), 'total': dados.get('total', 0), 'fila': dados.get('fila', [])})
                if notebook_nuvem():
                    dados = {'nuvem': True, 'online': dados.get('online', [])}   # convidado: joga direto da nuvem
                return self.json(dados)
            m = re.match(r'^/api/capa/([A-Z]{4}_\d{3}\.\d{2})\.jpg$', u.path)
            if m:
                cod = m.group(1)
                pd = pendrive()
                for e in ('jpg', 'png'):
                    arte = os.path.join(pd[0], 'ART', f'{cod}_COV.{e}') if pd else ''
                    if arte and os.path.exists(arte):
                        return self.responder(open(arte, 'rb').read(), f'image/{"jpeg" if e == "jpg" else e}',
                                              extra={'Cache-Control': 'max-age=86400'})
                d = baixar_capa(cod)
                if d is None:
                    return self.json({'erro': 'sem capa no acervo'}, 404)
                return self.responder(d, 'image/jpeg')
            if u.path == '/api/tarefas':
                return self.json(sorted(TAREFAS.values(), key=lambda t: -t['id']))
            if u.path == '/api/box/listar':
                pd = pendrive()
                if not pd:
                    raise Erro('sem pendrive na box')
                rel = relativo_seguro(q.get('c'))
                base = os.path.join(pd[0], rel)
                itens = []
                for e in os.scandir(base):
                    try:
                        itens.append({'nome': e.name, 'pasta': e.is_dir(), 'tam': 0 if e.is_dir() else e.stat().st_size,
                                      'protegido': bool(BOX_PROTEGIDOS.match(os.path.join(rel, e.name)))})
                    except OSError:
                        pass
                itens.sort(key=lambda i: (not i['pasta'], i['nome'].lower()))
                return self.json({'caminho': '/' + rel, 'itens': itens, 'livre': livre_pendrive()})
            if u.path == '/api/box/baixar':
                pd = pendrive()
                cam = os.path.join(pd[0], relativo_seguro(q.get('c'))) if pd else ''
                if not cam or not os.path.isfile(cam):
                    raise Erro('arquivo não encontrado')
                return self.enviar_arquivo(cam)
            if u.path == '/api/ps2/listar':
                return self.json({'caminho': q.get('c'), 'itens': ps2_listar(q.get('c'))})
            if u.path == '/api/ps2/baixar':
                c = caminho_ps2(q.get('c'))
                os.makedirs(ARQUIVOS, exist_ok=True)
                _rotulo_n[0] += 1
                nome = f'baixado-{_rotulo_n[0]}'
                ps2_op(0, c, f'host:arquivos/{nome}', espera=600)
                arq = os.path.join(ARQUIVOS, nome)
                try:
                    return self.enviar_arquivo(arq, os.path.basename(c))
                finally:
                    os.remove(arq)
            if u.path == '/api/ps2/pedido':
                return self.responder(nav('pedido').encode())
            if u.path == '/api/celular':
                return self.json(celular())
            if u.path == '/api/kits':
                return self.json({'kits': kits_com_jogos(), 'servidores': kits_urls()})
            return self.json({'erro': 'não encontrado'}, 404)
        except Erro as e:
            return self.json({'erro': str(e)}, 400)
        except Exception as e:
            log('GET', u.path, repr(e))
            return self.json({'erro': str(e)}, 500)

    def enviar_arquivo(self, caminho, nome=None):
        tam = os.path.getsize(caminho)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(tam))
        nome = nome or os.path.basename(caminho)
        self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{urllib.parse.quote(nome)}")
        self.end_headers()
        with open(caminho, 'rb') as f:
            while True:
                d = f.read(1 << 20)
                if not d:
                    break
                self.wfile.write(d)

    def receber_para(self, escritor):
        n = int(self.headers.get('Content-Length') or 0)
        while n > 0:
            d = self.rfile.read(min(n, 1 << 20))
            if not d:
                raise Erro('o envio parou no meio')
            escritor.write(d)
            n -= len(d)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = {a: b[0] for a, b in urllib.parse.parse_qs(u.query).items()}
        try:
            if not self.chave_ok():
                return self.json({'erro': 'chave da central errada'}, 403)
            if u.path == '/api/online/instalar':   # botão do app instalador: 1 clique = ISO no pendrive + VMC
                if notebook_nuvem():   # convidado: o jogo roda vindo direto do servidor do autor pela internet
                    return self.json({'ok': False, 'msg': 'no modo nuvem o jogo roda direto do servidor — não precisa instalar (basta primeiro entrar no jogo)'})
                corpo = self.corpo_json()
                try:
                    return self.json(json.loads(notebook_pedir('/api/online/instalar',
                                                               {'id': corpo.get('id'), 'arquivo': corpo.get('arquivo')}).read()))
                except urllib.error.HTTPError as e:
                    return self.json({'erro': e.read().decode(errors='replace')[:200] or f'HTTP {e.code}'}, 502)
                except (OSError, ValueError) as e:
                    return self.json({'erro': f'notebook fora do ar: {e}'}, 502)
            if u.path == '/api/controle':   # lista de eventos do touchpad/teclado
                evs = self.corpo_json()
                r = 'ok'
                for ev in evs if isinstance(evs, list) else [evs]:
                    if ev.get('tipo') == 'texto':
                        ev['texto'] = str(ev.get('texto', ''))[:120]
                    r = nav('remoto ' + json.dumps(ev, ensure_ascii=False), 4)
                return self.json({'ok': r == 'ok', 'resposta': r})
            if u.path == '/api/box/enviar':   # corpo = o arquivo; c = caminho de destino no pendrive
                pd = pendrive()
                if not pd:
                    raise Erro('sem pendrive na box')
                rel = relativo_seguro(q.get('c'))
                n = int(self.headers.get('Content-Length') or 0)
                if n > livre_pendrive() - (16 << 20):
                    raise Erro('falta espaço no pendrive da box')
                destino = os.path.join(pd[1], rel)
                root(f'mkdir -p {shlex.quote(os.path.dirname(destino))}')
                with GravarRoot(destino + '.parcial') as g:
                    self.receber_para(g)
                root(f'mv {shlex.quote(destino + ".parcial")} {shlex.quote(destino)}')
                return self.json({'ok': True})
            corpo = self.corpo_json()
            if u.path == '/api/capas/baixar':
                cods = corpo.get('codigos')
                return self.json(tarefa('Capas no pendrive da box', capas_para_box, set(cods) if cods else None))
            if u.path in ('/api/box/apagar', '/api/box/pasta', '/api/box/renomear'):
                pd = pendrive()
                if not pd:
                    raise Erro('sem pendrive na box')
                rel = relativo_seguro(corpo.get('c'))
                if not rel or (u.path != '/api/box/pasta' and BOX_PROTEGIDOS.match(rel)):
                    raise Erro('pasta protegida')
                cam = shlex.quote(os.path.join(pd[1], rel))
                if u.path == '/api/box/apagar':
                    root(f'rm -rf {cam}')
                elif u.path == '/api/box/pasta':
                    root(f'mkdir -p {cam}')
                else:
                    novo = os.path.basename(corpo.get('novo') or '')
                    if not novo or novo in ('.', '..'):
                        raise Erro('nome novo inválido')
                    root(f'mv {cam} {shlex.quote(os.path.join(pd[1], os.path.dirname(rel), novo))}')
                return self.json({'ok': True})
            if u.path == '/api/ps2/apagar':
                c = caminho_ps2(corpo.get('c'), gravar=True)
                ps2_op(7 if corpo.get('pasta') else 3, c, espera=30)
                return self.json({'ok': True})
            if u.path == '/api/ps2/pasta':
                ps2_op(6, caminho_ps2(corpo.get('c'), gravar=True), espera=30)
                return self.json({'ok': True})
            if u.path == '/api/celular/registrar':
                return self.json(celular_registrar(corpo.get('url'), corpo.get('chave')))
            if u.path == '/api/celular/jogar':
                iso = iso_do_celular(corpo.get('nome'))   # o Neutrino abre DVD/<nome>; o udpfs acha pelo nome (CD também)
                r = nav('neutrino ' + iso['nome'])
                return self.json({'ok': r == 'ok', 'resposta': r})
            if u.path == '/api/celular/para-box':
                iso = iso_do_celular(corpo.get('nome'))
                return self.json(tarefa(f'{iso["nome"]} → pendrive da box', celular_para_box, iso['nome']))
            if u.path == '/api/celular/para-ps2':
                iso = iso_do_celular(corpo.get('nome'))
                r = nav(f'copiar2 host:celular/{iso["pasta"]}/{iso["nome"]}|mass:/{iso["pasta"]}/{iso["nome"]}|'
                        f'{iso["nome"]}|{iso["tam"]}')
                return self.json({'ok': r == 'ok', 'resposta': r})
            if u.path == '/api/kits/aplicar':
                return self.json(tarefa('Kit online', aplicar_kit, corpo.get('kit'), corpo.get('onde'), corpo.get('nome'),
                                        bool(corpo.get('forcar'))))
            if u.path == '/api/kits/desligar-dns':
                try:
                    os.remove(DNS_KIT)
                except OSError:
                    pass
                return self.json({'ok': True})
            if u.path == '/api/kits/desfazer':   # volta o ISO como era antes do patch do kit
                pd = pendrive()
                nome = os.path.basename(corpo.get('nome') or '')
                pasta_kit = os.path.join(KITS_DIR, re.sub(r'[^\w.-]', '_', corpo.get('kit') or ''))
                desfazer = os.path.join(pasta_kit, f'desfazer-{nome}.json')
                iso = next((os.path.join(pd[1], p, nome) for p in ('DVD', 'CD')
                            if pd and os.path.exists(os.path.join(pd[0], p, nome))), None)
                if not iso or not os.path.exists(desfazer):
                    raise Erro('não há patch deste kit aplicado nesse ISO')
                root(f'{shlex.quote(sys.executable)} {shlex.quote(os.path.abspath(__file__))} ppf-desfazer '
                     f'{shlex.quote(iso)} {shlex.quote(desfazer)}', timeout=600)
                return self.json({'ok': True})
            if u.path == '/api/kits/enviar':
                return self.json(enviar_kit(corpo))
            return self.json({'erro': 'não encontrado'}, 404)
        except Erro as e:
            return self.json({'erro': str(e)}, 400)
        except Exception as e:
            log('POST', u.path, repr(e))
            return self.json({'erro': str(e)}, 500)


class HCompleto(H):
    def do_POST(self):
        """POST /api/ps2/enviar?c=<destino no PS2>: guarda na box e manda o PS2 copiar (tarefa)."""
        u = urllib.parse.urlparse(self.path)
        if u.path != '/api/ps2/enviar':
            return super().do_POST()
        q = {a: b[0] for a, b in urllib.parse.parse_qs(u.query).items()}
        try:
            if not self.chave_ok():
                return self.json({'erro': 'chave da central errada'}, 403)
            c = caminho_ps2(q.get('c'), gravar=True)
            if not ps2_aberto():
                raise Erro('o navegador não está aberto no PS2')
            os.makedirs(ARQUIVOS, exist_ok=True)
            _rotulo_n[0] += 1
            nome = f'enviado-{_rotulo_n[0]}'
            arq = os.path.join(ARQUIVOS, nome)
            with open(arq, 'wb') as f:
                self.receber_para(f)
            tam = os.path.getsize(arq)

            def copiar(t):
                try:
                    ps2_op(0, f'host:arquivos/{nome}', c, tam=tam, espera=3600, t=t)
                    t['msg'] = f'✔ {c}'
                finally:
                    os.remove(arq)
            return self.json(tarefa(f'{os.path.basename(c)} → PS2', copiar))
        except Erro as e:
            return self.json({'erro': str(e)}, 400)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'ppf-aplicar':
        return ppf_aplicar(sys.argv[2], sys.argv[3], sys.argv[4])
    if len(sys.argv) > 1 and sys.argv[1] == 'ppf-desfazer':
        return ppf_desfazer(sys.argv[2], sys.argv[3])
    for d in (ARQUIVOS, CAPAS, KITS_DIR):
        os.makedirs(d, exist_ok=True)
    srv = ThreadingHTTPServer(('0.0.0.0', PORTA), HCompleto)
    srv.daemon_threads = True
    log(f'central do celular em http://0.0.0.0:{PORTA}/celular (pendrive: {pendrive()})')
    srv.serve_forever()


if __name__ == '__main__':
    main()
