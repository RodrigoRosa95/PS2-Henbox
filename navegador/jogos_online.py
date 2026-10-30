"""🎮 Jogos online da loja (25/10/2026): varre os grupos de WhatsApp (conta do bot, rota /varrer-jogos),
baixa ISO + VMC dos anúncios, organiza em ~/ps2-monitor/online/ com nomes oficiais e gera o
catalogo.json que alimenta a aba 🌐 "Games Online" da loja (/loja/api/online, servidor.py 8770).

A pasta fica no SSD do notebook (o 01TERA está 100% cheio). A instalação de 1 clique na loja cria
um link simbólico do ISO dentro de PS2_JOGOS/DVD (a fila da loja copia até o pendrivePS2 direitinho —
clicando em instalar, o jogo passa a se comportar como qualquer outro da loja) e manda o VMC como
kit para o kits_servidor (auto-aprovado), para instalar na Central em "Kits → aplicar".

CLI:  varrer | baixar <n.º-do-candidato> | baixar-tudo | organizar | catalogo | tudo | lista
      instalar <serial-ou-nome>   mensagem-teste <texto>   enviar <grupo> <texto>
"""
import base64, json, os, re, shutil, subprocess, sys, time, urllib.request, urllib.parse

PASTA = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(PASTA)                      # ~/ps2-monitor
ONLINE = os.path.join(BASE, 'online')              # programas: online/*.iso + online/vmc/*.bin + catalogo.json
JOGOS_DVD = os.path.join(os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2'), 'DVD')
CANDIDATOS = os.path.join(ONLINE, 'candidatos.json')
CATALOGO = os.path.join(ONLINE, 'catalogo.json')
VMC_DIR = os.path.join(ONLINE, 'vmc')
BOT = os.environ.get('ATSAPP_API_URL', 'http://localhost:8082')
KITS = os.environ.get('PS2_KITS', 'http://localhost:8792/kits/enviar')
TVBOX = os.environ.get('PS2_TVBOX', '192.168.4.79')
UNRAR = os.path.expanduser('~/.local/bin/unrar')
PEN = os.environ.get('PS2_TVBOX_USB', '/mnt/media_rw/1E0A-1F18')
GRUPO_TESTE = 'CLAUDE'
UA = 'PS2-Henbox (jogos_online)'


def log(*a):
    print(time.strftime('%d/%m %H:%M:%S'), *a, flush=True)


def _json_post(url, dados, timeout=90):
    req = urllib.request.Request(url, json.dumps(dados).encode(), {'Content-Type': 'application/json',
                                                                   'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---------------- varrer ----------------

def varrer():
    """Grupos com link na descrição → candidatos.json (id, nome, desc, links, vmc?, dns?)."""
    r = _json_post(BOT + '/varrer-jogos', {}, 90)
    grupos = r.get('grupos') or []
    os.makedirs(ONLINE, exist_ok=True)
    with open(CANDIDATOS + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(grupos, f, ensure_ascii=False, indent=1)
    os.replace(CANDIDATOS + '.tmp', CANDIDATOS)
    log(f'varridos {r.get("varridos")}: {len(grupos)} com links ({sum(1 for g in grupos if g.get("vmc"))} com VMC)')
    return grupos


def candidatos():
    try:
        return json.load(open(CANDIDATOS, encoding='utf-8'))
    except (OSError, ValueError):
        return []


def analisar(titulo, descricao, links):
    """Divide os links do anúncio: os rotulados como VMC (na linha do link, ou nome .psu/.vmc) de um lado;
    os demais são o jogo. A poeira técnica (tutorial, rede social) é enterrada de fora (ótimo)."""
    jogo, vmc = [], []
    for link in links:
        linha = next((l for l in descricao.splitlines() if link in l), link)
        alvo = os.path.basename(urllib.request.unquote(link.split('?')[0])).lower()
        rotulo = re.search(r'\bvmc\b|memory\s*card|memória\s*card', linha, re.I) or re.search(r'\.(psu|vmc)\b', alvo)
        if rotulo:
            vmc.append(link)
        elif not re.search(r'discord|chat\.whatsapp|t\.me|instagram|facebook|youtube|twitter|tiktok', link, re.I):
            jogo.append(link)
    return {'titulo': titulo, 'desc': descricao, 'jogo': jogo, 'vmc': vmc}


# ---------------- baixar ----------------

FLARESOLVERR = 'http://localhost:8191/v1'
UA_NAVEGADOR = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36'


def _derivanche(url):
    """Encurtadores (hdlvl.dev, bit.ly…) dão 301 para o MediaFire; o urllib segue (e morre no 403 do MF).
    Esta versão para EM CADA salto (não segue) e devolve o destino final — que o link_direto já sabe tratar.
    O 403 do MediaFire NÃO é erro real: é o aviso de que a viagem já chegou lá (ele exige JavaScript)."""
    sem = urllib.request.build_opener(_NaoSegue)
    for _ in range(6):
        req = urllib.request.Request(url, headers={'User-Agent': UA_NAVEGADOR})
        try:
            with sem.open(req, timeout=30) as r:
                return r.geturl()
        except urllib.error.HTTPError as e:
            loc = e.headers.get('Location')
            if loc and e.code in (301, 302, 303, 307, 308):
                url = urllib.request.urljoin(url, loc)
                continue
            if e.code in (403, 404) and 'mediafire.com' in url:
                return url   # chegou no MediaFire: será tratado pelo FlareSolverr no link_direto
            raise
    return url


class _NaoSegue(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def link_direto(url):
    """MediaFire passa pelo FlareSolverr (desafio do Cloudflare); o resto é baixado direto. = evento_online."""
    if 'mediafire.com' in url:
        return _mídia(url), None
    return url, None


def _mídia(url):
    corpo = json.dumps({'cmd': 'request.get', 'url': url, 'maxTimeout': 60000}).encode()
    req = urllib.request.Request(FLARESOLVERR, corpo, {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        h = (json.loads(r.read()).get('solution') or {}).get('response') or ''
    m = re.search(r'href="(https://download[^"]+)"', h)
    if not m:
        raise RuntimeError('o MediaFire não mostrou o botão de download (arquivo removido?)')
    nome = re.search(r'class="filename">([^<]+)', h)
    return m.group(1), (nome.group(1).strip() if nome else None)


def gather(url):
    """Devolve (link de download, nome do arquivo) resolvendo encurtador→MediaFire/drive/direta (25/10/2026)."""
    real = _derivanche(url)
    if 'mega.nz' in real:
        raise RuntimeError('link do Mega não suportado ainda (o Drive e o MediaFire sim)')   # cod2/cod3 do COD? podia dar pra baixar com API, fica pra depois
    if 'drive.google.com' in real:
        m = re.search(r'(?:/d/|id=)([\w-]{20,})', real)
        return (f'https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t' if m else real), None
    if 'mediafire.com' in real:
        return _mídia(real)
    nome = urllib.request.unquote(real.split('?')[0].rsplit('/', 1)[-1])
    return real, (nome if ('.' in nome and 2 < len(nome) < 140) else None)


def _baixar(url, pasta):
    """Baixa o link (e extrai rar/zip/7z se for comprimido); devolve a pasta com o conteúdo."""
    os.makedirs(pasta, exist_ok=True)
    url2, nome = gather(url)
    nome = os.path.basename(nome or urllib.request.unquote(url2.split('?')[0].rsplit('/', 1)[-1]).replace('+', ' ') or 'baixado.bin')
    arq = os.path.join(pasta, nome)
    log('baixando:', nome or url)
    req = urllib.request.Request(url2, headers={'User-Agent': UA_NAVEGADOR})
    feito = 0
    with urllib.request.urlopen(req, timeout=60) as r:
        cd = r.headers.get('Content-Disposition', '')
        m = re.search(r'filename="?([^";]+)"?', cd)          # o Drive (e servidores sérios) spoiled the file name after download
        if m and m.group(1).strip():
            nome = os.path.basename(m.group(1).strip())
            arq = os.path.join(pasta, nome)
        with open(arq, 'wb') as f:
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
                feito += len(bloco)
    if feito < 4096:
        head = open(arq, 'rb').read(400)
        raise RuntimeError('muito pequeno: ' + head.decode('utf-8', 'replace')[:150])
    log('baixado:', f'{feito >> 20} MB', nome)
    if nome.lower().endswith(('.rar', '.zip', '.7z')):
        log('extraindo…')
        cmd = ([UNRAR, 'x', '-o+', '-y', arq, pasta + '/'] if nome.lower().endswith('.rar') and os.path.exists(UNRAR)
               else ['7z', 'x', '-y', '-o' + pasta, arq])
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError(os.path.basename(cmd[0]) + ': ' + ((p.stdout + p.stderr).strip().splitlines() or ['?'])[-1][:120])
        os.remove(arq)
    return pasta


def _ache_vmc(pasta):
    for d, _, ns in os.walk(pasta):
        for n in ns:
            f = os.path.join(d, n)
            try:
                if os.path.getsize(f) <= 64 * 1024 ** 2 and b'Sony PS2 Memory Card Format' in open(f, 'rb').read(0x40):
                    return f
            except OSError:
                pass
    return None


def _serial(iso):
    sys.path.insert(0, PASTA)
    try:
        from ra_hash import hash_ps2
        return hash_ps2(iso)[1]
    except Exception as e:
        log('serial falhou:', e)
        return ''


def _acervo_com_serial(cod):
    """Jogo do acervo da loja com esse serial → nome oficial e capa aproveitados (fonte de verdade: coleção)."""
    if not cod:
        return '', False
    p = os.path.join(os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2'), 'DVD')
    for sub in ('DVD', 'CD'):
        pasta = os.path.join(os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2'), sub)
        try:
            for arq in os.listdir(pasta):
                if arq.upper().startswith(cod.replace('_', '_').upper()) and arq.lower().endswith('.iso'):
                    base = re.sub(r'\.iso$', '', arq, flags=re.I)
                    return base.split('.', 1)[1] if '.' in base else base, True
        except OSError:
            pass
    return '', False


_SUCATA = re.compile(r'\[[^\]]*\]|\([^)]*\)|\b(br|pt-?br|ntsc|pal|rev\d*|ps2|playstation\s*2|game|jogo)\b|[-_.]| {2,}', re.I)
_SERIAL_COMPLETO = re.compile(r'^([A-Z]{4}_\d{3}\.\d{2})\.(.+)$')


def _titulo_livre(nome_iso):
    base = os.path.splitext(os.path.basename(nome_iso))[0].strip()
    m = _SERIAL_COMPLETO.fullmatch(base)
    if m:                       # 'SLUS_210.26.Battlefield 2 - Modern Combat' → só o título (o serial fica de fora)
        base = m.group(2)
    titular = re.sub(r'\[[^\]]*\]|\([^)]*\)', ' ', base)
    titular = _SUCATA.sub(' ', titular)
    titular = re.sub(r'\s+', ' ', titular).strip(' -_.')
    titular = re.sub(r'\s+(online|na net)$', '', titular, flags=re.I)   # 'Tekken 5 Online' → 'Tekken 5'
    return titular[:60] or base[:60]


def _slug(n):
    s = re.sub(r'[^A-Za-z0-9]+', '-', n).strip('-').lower()
    return s[:40] or 'jogo'


def _mandar_kit(cod, titulo, vmc_arq, dns):
    """O VMC vira kit no kits_servidor (injeta automaticamente; central em "Kits → aplicar" aplica no pendrive)."""
    dados = {'codigo': cod, 'titulo': titulo[:80], 'dns': 'ip-de-Rede' if False else (dns or ''), 'servidor': '',
             'autor': 'jogos online (WhatsApp)', 'notas': f'VMC veio do anúncio de grupo ({time.strftime("%d/%m/%Y %H:%M")})',
             'arquivos': [{'nome': 'vmc.ps2', 'dados': base64.b64encode(open(vmc_arq, 'rb').read()).decode()}]}
    r = _json_post(KITS, dados, 90)
    if not r.get('ok'):
        raise RuntimeError(r.get('erro') or 'o servidor de kits recusou o VMC')
    p = subprocess.run([sys.executable, os.path.join(PASTA, 'kits_servidor.py'), 'aprovar', str(r['numero'])],
                       capture_output=True, text=True)
    kit = os.path.basename((p.stdout or '').strip().split()[-1]) if p.returncode == 0 else ''
    if not kit:
        raise RuntimeError('kit entrou, mas a aprovação falhou: ' + (p.stderr.strip() or '?')[:100])
    log('kit:', kit)
    return kit


APERADORES = None


def baixar(idx):
    """Candidato n.º idx (1 baseado) → baixa jogo (+ VMC quando há), organiza, soma no catalogo."""
    cs = candidatos()
    if not (1 <= idx <= len(cs)):
        return log(f'candidato inválido: {idx} de {len(cs)}')
    bruto = cs[idx - 1]
    a = analisar(bruto.get('nome', ''), bruto.get('desc', ''), bruto.get('links', []))
    log('candidato', idx, ':', a['titulo'], f'({len(a["jogo"])} link(s) de jogo, {len(a["vmc"])} de VMC)')
    if not a['jogo'] and not a['vmc']:
        return log('nada para baixar nesse candidato')
    trabalho = os.path.join('/tmp/ops', 'online-' + _slug(a['titulo']))   # baixar fora de casa (HD cheio)
    if os.path.exists(trabalho):
        shutil.rmtree(trabalho, ignore_errors=True)
    iso = vmc_arq = None
    try:
        if a['jogo']:
            _baixar(a['jogo'][0], trabalho)
            isos = [os.path.join(d, n) for d, _, ns in os.walk(trabalho) for n in ns if n.lower().endswith('.iso')]
            if not isos:
                raise RuntimeError('não veio nenhum .iso no anúncio')
            iso = max(isos, key=os.path.getsize)
            vmc_arq = vmc_arq or _ache_vmc(trabalho)   # o VMC vem escondido NO pacote do jogo (VMC.geral em anúncios de grupos)
        if a['vmc']:
            vpasta = _baixar(a['vmc'][0], trabalho + '-vmc')
            vmc_arq = _ache_vmc(vpasta)
            if not vmc_arq:
                log('aviso: o link chamado de VMC não veio com memory card.')
    except Exception as e:
        log('falhou:', e)
        shutil.rmtree(trabalho, ignore_errors=True)
        return
    # ---- organizar (nome oficial: serial + título, preferindo o acervo) ----
    cod = _serial(iso) if iso else ''
    titulo_acervo, tem_acervo = _acervo_com_serial(cod)
    titulo = titulo_acervo or _titulo_livre(iso or a['titulo'])
    dns = ''
    m = re.search(r'dns\b[^\n]{0,20}?\b(\d{1,3}(?:\.\d{1,3}){3})', a['desc'], re.I) or \
        re.search(r'dns\b[^\n]{0,20}?\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)', a['desc'], re.I)
    if m:
        dns = m.group(1)
    os.makedirs(ONLINE, exist_ok=True)
    os.makedirs(VMC_DIR, exist_ok=True)
    registro = {'id': cod or _slug(titulo), 'nome': titulo, 'serial': cod, 'dns': dns,
                'vmc': '', 'vmc_serial': '', 'quando': int(time.time())}
    if vmc_arq:
        vnome = (cod or _slug(titulo)) + '.ps2'
        vfinal = os.path.join(VMC_DIR, vnome)
        shutil.move(vmc_arq, vfinal)
        registro['vmc'] = 'vmc/' + vnome
        registro['vmc_serial'] = vnome
    if iso:
        final = f'{cod}.{titulo}.iso' if cod else f'{titulo}.iso'
        final = re.sub(r'[\\/:*?"<>|]', '', final)
        destino = os.path.join(ONLINE, final)
        if os.path.exists(destino):
            os.remove(destino)
        shutil.move(iso, destino)
        registro['arquivo'] = final
        registro['tamanho'] = os.path.getsize(destino)
        capa = os.path.join(BASE, 'capas', cod + '.jpg')
        registro['capa'] = f'capas/{cod}.jpg' if cod and os.path.exists(capa) else ''
        registro['tem_acervo'] = tem_acervo
        shutil.rmtree(trabalho, ignore_errors=True)
        log('organizado:', final, f'({registro["tamanho"] >> 20} MB)')
    if registro.get('vmc') and cod:
        try:
            registro['kit'] = _mandar_kit(cod, titulo, os.path.join(ONLINE, registro['vmc']), dns)
        except Exception as e:
            log('kit falhou:', e)
    entrada(registro)
    catalogo()


def entrada(reg):
    idem = reg['id']
    outros = [g for g in ler_catalogo().get('online', []) if g.get('id') != idem]
    outros.append(reg)
    salv_catalog({'online': outros})


# ---------------- catálogo ----------------

def ler_catalogo():
    try:
        return json.load(open(CATALOGO, encoding='utf-8'))
    except (OSError, ValueError):
        return {'online': []}


C_T = None


def salv_catalog(dados):
    with open(CATALOGO + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(CATALOGO + '.tmp', CATALOGO)


def catalogo():
    """Escreve catalogo.json e devolve o objeto pronto para /api/online (o instalado vem do pendrive)."""
    dados = ler_catalogo()
    pen = os.path.join(PEN, 'DVD')
    try:
        no_pen = {a.lower() for a in os.listdir(pen)}
    except OSError:
        no_pen = set()
    for j in dados.get('online', []):
        full = os.path.join(ONLINE, j.get('arquivo', '')) if j.get('arquivo') else None
        if not j.get('capa'):
            cod = j.get('serial') or j.get('id') or ''
            if cod and os.path.exists(os.path.join(BASE, 'capas', cod + '.jpg')):
                j['capa'] = 'capas/' + cod + '.jpg'
        j['existe'] = bool(full and os.path.isfile(full))
        j['instalado'] = j.get('arquivo', '').lower() in no_pen
        j['tamanho'] = j.get('tamanho') or (os.path.getsize(full) if full and os.path.isfile(full) else 0)
    salv_catalog(dados)
    return dados


def organizar():
    """Re-passa os jogos que já estão na pasta renovando o catalogo (útil depois de mexer na mão)."""
    catalogo()


# ---------------- instalar (1 clique na loja) ----------------

def buscar(jid):
    jid = str(jid or '').lower()
    for j in ler_catalogo().get('online', []):
        if j['id'].lower() == jid or j.get('serial', '').lower() == jid or j.get('arquivo', '').lower() == jid:
            return j
    return None


def instalar(jid):
    """O clique da loja: ISO → fila da loja (instala no pendrive como um jogo normal) + kit de VMC já aprovado."""
    j = buscar(jid)
    if not j:
        return False, 'jogo não está no catálogo online ( rode jogos_online.py catalogo ).'
    if not j.get('arquivo'):
        return False, 'esse anúncio só tinha o VMC, sem o jogo.'
    iso_local = os.path.join(ONLINE, j['arquivo'])
    if not os.path.isfile(iso_local):
        return False, 'o ISO sumiu da pasta online (rode: jogos_online.py organizar).'
    link = os.path.join(JOGOS_DVD, j['arquivo'])
    try:
        if not os.path.lexists(link):
            os.symlink(iso_local, link)
    except OSError as e:
        return False, f'link no acervo falhou: {e}'
    os.environ.setdefault('PS2_JOGOS', '/media/rodrigo/01TERA/PS2')
    sys.path.insert(0, BASE)
    import loja as loja_mod
    ok, msg = loja_mod.instalar(j['arquivo'])
    if not ok:
        return ok, msg
    return True, (j.get('kit') and f'{msg} Kit de VMC: {j["kit"]} (aplicar na Central: Kits → aplicar).'
                  or msg + ' (esse anúncio não tinha VMC)')


# ---------------- WhatsApp ----------------

def enviar_para(nome_grupo, texto):
    try:
        r = _json_post(BOT + '/enviar-nome', {'grupo': nome_grupo, 'texto': texto}, 30)
    except Exception as e:
        return f'⚠️ bot fora do ar ({e})'
    if not r.get('success'):
        return '⚠️ ' + (r.get('erro') or '?')
    return f'✅ entregue em *{r.get("grupo", nome_grupo)}*'


def mensagem_teste(texto):
    """Mensagem de teste para o grupo ${GRUPO_TESTE} (pedida pelo usuário)."""
    texto = texto or f'🤖 Teste do bot ({time.strftime("%d/%m %H:%M")}) — pipeline de *games online* rodando!'
    r = enviar_para(GRUPO_TESTE, texto)
    log('mensagem teste:', r)
    return r


# ---------------- CLI ----------------

def cli(argv):
    if not argv or argv[0] in ('varrer',):
        cs = varrer()
        for i, g in enumerate(cs, 1):
            a = analisar(g.get('nome', ''), g.get('desc', ''), g.get('links', []))
            print(f'{i:>3}. {g["nome"][:46]:46} jogo:{len(a["jogo"])} vmc:{len(a["vmc"])}'
                  + (f' · dns:{_dns(a)}' if a else ''))
        if argv[:1] == ['varrer']:
            catalogo()
        return
    if argv[0] == 'lista':
        for i, g in enumerate(candidatos(), 1):
            print(f'{i:>3}. {g["nome"][:60]:60} links:{len(g.get("links", []))}')
        return
    if argv[0] in ('baixar', 'baixar-tudo'):
        if argv[0] == 'baixar':
            return baixar(int(argv[1]))
        n = len(candidatos())
        for i in range(1, n + 1):
            baixar(i)
        return
    if argv[0] == 'tudo':
        varrer()
        n = len(candidatos())
        for i in range(1, n + 1):
            try:
                baixar(i)
            except Exception as e:
                log('candidato', i, 'falhou:', e)
        return catalogo()
    if argv[0] in ('catalogo', 'organizar'):
        return print(json.dumps(catalogo(), ensure_ascii=False)[:600])
    if argv[0] == 'instalar':
        r = instalar(argv[1])
        return print(r[1])
    if argv[0] == 'mensagem-teste':
        return print(mensagem_teste(' '.join(argv[1:]) or ''))
    if argv[0] == 'enviar':
        return print(enviar_para(argv[1], ' '.join(argv[2:]) or ''))
    print(__doc__)


def _dns(a):
    m = re.search(r'dns\b[^\n]{0,20}?\b(\d{1,3}(?:\.\d{1,3}){3})', a['desc'], re.I)
    return m.group(1) if m else '?'


if __name__ == '__main__':
    cli(sys.argv[1:])
