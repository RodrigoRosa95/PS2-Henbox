#!/usr/bin/env python3
"""Evento online do PS2 (pedido do usuário 23/10/2026: "faça todo o fluxo"). Roda no notebook.

Os anúncios das partidas (Hardlevel e afins) chegam assim:
    Star Wars: Battlefront 1 começa em 2H (20H GMT-3)
    DNS: 45.7.228.197
    Server Dedicated: AlexGHD's_Server
    LINK DO JOGO AQUI : https://www.mediafire.com/file/...
Colando o texto com /evento no grupo de testes do WhatsApp (claude — NUNCA o grupo Jellyflix), este script:
  1. lê jogo, horário, DNS, servidor, link e tutoriais e guarda em eventos_online.json;
  2. confere se o jogo já está na biblioteca (01TERA/PS2/DVD e pendrive da TV box); se não estiver, "/evento baixar"
     baixa do MediaFire (pelo FlareSolverr: a página tem o desafio do Cloudflare), extrai o .rar com o 7z e põe o ISO
     em DVD/ como SLUS_xxx.xx.Nome.iso (a loja e o "jogo em nuvem" já enxergam);
  3. a TV box busca os eventos (videos_https /eventos) e, na janela do evento (1 h antes até 5 h depois), o
     henbox-root.sh desvia o DNS do PS2 que está no cabo da box para o DNS do evento — nada a digitar no PS2;
  4. cron */5 (vigiar): 2 h antes confere jogo + DNS + TV box e avisa no WhatsApp; 15 min antes avisa de novo.

  evento_online.py novo            texto do anúncio pela entrada padrão → resumo (o que o bot responde)
  evento_online.py lista | cancelar [N] | baixar [N] | vmc [N] | vigiar | ler (só mostra o que entendeu, sem salvar)
  Quando o anúncio traz o link do VMC (memory card de rede pronto, uso + kit na descrição), o /evento baixar puxa
  o jogo e o VMC juntos: o VMC vira kit aprovado no servidor de kits e o DNS do evento vai junto no kit.
"""
import base64
import datetime as dt, json, os, re, shutil, socket, struct, subprocess, sys, time, unicodedata, urllib.request

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'eventos_online.json')
LOG = os.path.join(PASTA, 'evento_online.log')
JOGOS = os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2')
PENDRIVE_BOX = '/mnt/tvbox-ps2/DVD'   # Samba [PS2] da TV box (automount)
BAIXANDO = os.path.join(JOGOS, 'BAIXANDO-EVENTO')
TVBOX = os.environ.get('PS2_TVBOX', '192.168.4.79')
FLARESOLVERR = 'http://localhost:8191/v1'
UNRAR = os.path.expanduser('~/.local/bin/unrar')
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
FUSO = dt.timezone(dt.timedelta(hours=-3))   # Brasília (sem horário de verão)
ANTES, DEPOIS = 3600, 5 * 3600   # janela do DNS do evento na TV box
# domínios usados para ver se o DNS do evento responde (ele só atende os dos jogos; NXDOMAIN também vale)
DOMINIOS_TESTE = ['battlefront-ps2.svo.online.scea.com', 'ps2.ea.com', 'google.com']


def env():
    d = {}
    try:
        for l in open(os.path.expanduser('~/.env')):
            if '=' in l and not l.lstrip().startswith('#'):
                k, v = l.split('=', 1)
                d[k.strip()] = v.strip().strip('"\'')
    except OSError:
        pass
    return d


def grupo_whats():
    """Só o grupo de testes (claude). O grupo Jellyflix (anúncios) fica de fora de propósito."""
    e = env()
    g = e.get('EVENTO_PS2_GRUPO') or e.get('JELLYFLIX_WHATS_GRUPO_ADMIN', '')
    return '' if g and g == e.get('JELLYFLIX_WHATS_GRUPO_ANUNCIOS') else g


def log(*a):
    with open(LOG, 'a') as f:
        print(time.strftime('%d/%m %H:%M:%S'), *a, file=f)


def whats(msg):
    g = grupo_whats()
    if not g:
        return log('sem grupo do WhatsApp:', msg[:60])
    url = env().get('ATSAPP_API_URL', 'http://localhost:8082').rstrip('/') + '/send'
    try:
        req = urllib.request.Request(url, json.dumps({'number': g, 'message': msg}).encode(),
                                     {'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        log('WhatsApp falhou:', e)


def ler_eventos():
    try:
        return json.load(open(ARQ, encoding='utf-8'))
    except (OSError, ValueError):
        return []


def salvar(evs):
    with open(ARQ + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(evs, f, ensure_ascii=False, indent=1)
    os.replace(ARQ + '.tmp', ARQ)


# ---------------- leitura do anúncio ----------------

def compacto(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)


def ler_anuncio(texto, agora=None):
    agora = agora or dt.datetime.now(FUSO)
    linhas = [l.strip() for l in texto.strip().splitlines() if l.strip()]
    ev = {'jogo': '', 'inicio': None, 'dns': [], 'servidor': '', 'link': '', 'vmc': '', 'tutoriais': [], 'texto': texto.strip()}
    if linhas:
        m = re.match(r'^(.*?)\s+(?:come[cç]a|hoje|amanh[aã]|dia\s+\d|[àa]s\s+\d|\d{1,2}\s*[hH:]\d{0,2}\b|-\s)', linhas[0], re.I)
        ev['jogo'] = (m.group(1) if m else linhas[0]).strip(' :-–*_')
    ev['dns'] = [ip for ip in re.findall(r'DNS[^\n\d]{0,20}((?:\d{1,3}\.){3}\d{1,3})(?:[^\n\d]+((?:\d{1,3}\.){3}\d{1,3}))?', texto, re.I)
                 for ip in ip if ip]
    m = re.search(r'serv(?:er|idor)[^:\n]*:\s*(.+)', texto, re.I)
    ev['servidor'] = m.group(1).strip() if m else ''
    urls = re.findall(r'https?://\S+', texto)
    # VMC (memory card de rede pronto) na frente: o link numa linha que fala VMC é o do memory card, não o do jogo
    for l in linhas:
        if re.search(r'\bvmc\b', l, re.I):
            mv = re.search(r'https?://\S+', l)
            if mv:
                ev['vmc'] = mv.group(0).rstrip('.,;)')
                if not re.search(r'https?://\S+.*https?://\S+', l):
                    break
    for u in urls:
        if u == ev['vmc']:
            continue
        if re.search(r'youtu\.?be', u):
            linha = next((l for l in linhas if u in l), '')
            rotulo = linha.split(u)[0].strip(' :-–') or 'Tutorial'
            ev['tutoriais'].append({'titulo': rotulo, 'url': u})
        elif not ev['link']:
            ev['link'] = u
    if not ev['vmc']:
        sem_yt = [u for u in urls if 'youtu' not in u]
        if len(sem_yt) >= 2 and ev['link'] == sem_yt[0]:
            ev['vmc'] = sem_yt[1]   # dois links sem rótulo: o segundo costuma ser o VMC
    ev['inicio'] = ler_horario(texto, agora)
    return ev


def ler_horario(texto, agora):
    """Horário absoluto (o "20H GMT-3" entre parênteses) ou, sem ele, o relativo ("começa em 2H")."""
    data = agora.date()
    m = re.search(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', texto)
    if m:
        ano = int(m.group(3)) if m.group(3) else agora.year
        data = dt.date(ano + 2000 if ano < 100 else ano, int(m.group(2)), int(m.group(1)))
    elif re.search(r'amanh[aã]', texto, re.I):
        data += dt.timedelta(days=1)
    for m in re.finditer(r'(?<![\d.])(\d{1,2})\s*(?:[hH]\s*(\d{2})?|:(\d{2}))(?![\w.])(\s*(?:GMT|UTC)\s*([+-]\s*\d{1,2}))?', texto):
        antes = texto[max(0, m.start() - 4):m.start()].lower()
        if re.search(r'em\s*$', antes):   # "em 2H" é relativo
            continue
        h, mi = int(m.group(1)), int(m.group(2) or m.group(3) or 0)
        if h > 23 or mi > 59:
            continue
        fuso = dt.timezone(dt.timedelta(hours=int(m.group(5).replace(' ', '')))) if m.group(5) else FUSO
        quando = dt.datetime.combine(data, dt.time(h, mi), fuso)
        if quando < agora - dt.timedelta(hours=6) and not re.search(r'\d{1,2}/\d{1,2}', texto):
            quando += dt.timedelta(days=1)   # 20h anunciado de madrugada já passou: é o de amanhã
        return int(quando.timestamp())
    m = re.search(r'em\s*(\d{1,2})\s*(?:h|hora)', texto, re.I)
    if m:
        return int((agora + dt.timedelta(hours=int(m.group(1)))).timestamp()) // 300 * 300
    return None


# ---------------- biblioteca ----------------

def no_acervo(jogo):
    """[(onde, arquivo)] dos ISOs com o nome do jogo (Battlefront ≠ Battlefront II)."""
    alvo = compacto(re.sub(r'\b(1|i)\s*$', '', jogo.replace(':', ' ')).strip())
    achados = []
    for onde, pasta in (('notebook', os.path.join(JOGOS, 'DVD')), ('notebook', os.path.join(JOGOS, 'CD')),
                        ('TV box', PENDRIVE_BOX)):
        try:
            nomes = os.listdir(pasta)
        except OSError:
            continue
        for n in nomes:
            if not n.lower().endswith('.iso'):
                continue
            base = re.sub(r'^[A-Z]{4}_\d{3}\.\d{2}\.', '', n[:-4])
            c = compacto(base)
            resto = c[len(alvo):] if c.startswith(alvo) else None
            # depois do nome só variação do mesmo jogo (PT-BR, dublado, 60 Hz…): "Black" ≠ "Blackhawk", ≠ "2"
            if alvo and resto is not None and re.fullmatch(r'(i|1|ptbr|pt|br|dub|dublado|ntsc|pal|usa|eua|60hz|abnt2|v\d+)*', resto):
                achados.append((onde, n))
    return achados


# ---------------- testes ----------------

def consulta_dns(servidor, nome, timeout=3):
    pk = struct.pack('>HHHHHH', os.getpid() & 0xffff, 0x100, 1, 0, 0, 0)
    pk += b''.join(bytes([len(p)]) + p.encode() for p in nome.split('.')) + b'\0' + struct.pack('>HH', 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    t = time.time()
    try:
        s.sendto(pk, (servidor, 53))
        s.recv(512)
        return int((time.time() - t) * 1000)
    finally:
        s.close()


def dns_responde(servidor):
    for nome in DOMINIOS_TESTE:
        for _ in range(2):
            try:
                return consulta_dns(servidor, nome)
            except OSError:
                pass
    return None


def estado_box():
    try:
        with urllib.request.urlopen(f'http://{TVBOX}:8780/evento/estado.json', timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ---------------- textos ----------------

def hora(ts):
    d = dt.datetime.fromtimestamp(ts, FUSO)
    hoje = dt.datetime.now(FUSO).date()
    dia = 'hoje' if d.date() == hoje else 'amanhã' if d.date() == hoje + dt.timedelta(days=1) else d.strftime('%d/%m')
    return f'{dia} às {d:%H:%M}'


def resumo(ev, n=None):
    acervo = no_acervo(ev['jogo'])
    linhas = [f'🎮 *{ev["jogo"] or "?"}*' + (f' (evento {n})' if n else ''),
              f'🕗 {hora(ev["inicio"])}' if ev.get('inicio') else '🕗 horário não entendido',
              f'🌐 DNS: {", ".join(ev["dns"])}' if ev['dns'] else '🌐 DNS: não veio no anúncio',
              f'🖥️ Servidor: {ev["servidor"]}' if ev['servidor'] else '']
    if acervo:
        linhas.append('💿 Jogo: ✅ já está aqui (' + ', '.join(f'{o}: {a}' for o, a in acervo[:2]) + ')')
    elif ev.get('baixando'):
        linhas.append(f'💿 Jogo: ⬇ {ev["baixando"]}')
    elif ev.get('link'):
        linhas.append('💿 Jogo: ❌ não está na biblioteca. Responda */evento baixar* para baixar e pôr no PS2.')
    else:
        linhas.append('💿 Jogo: ❌ não está na biblioteca e o anúncio não tem link.')
    if ev.get('kit'):
        linhas.append(f'💾 VMC: ✅ kit {ev["kit"]} na central da TV box (Kits → aplicar; leva o DNS do evento junto)')
    elif ev.get('vmc'):
        linhas.append('💾 VMC: ⬇ *evento vmc* baixa o memory card do link e aprova como kit na central')
    else:
        linhas.append('💾 VMC: sem link (quem já tem perfil de rede continua com o dele)')
    linhas.append('📡 Com o PS2 no cabo da TV box, o DNS do evento entra sozinho 1 h antes (deixe a rede do jogo em '
                  'automático). PS2 no roteador: ponha o DNS acima na configuração de rede do jogo.')
    for t in ev.get('tutoriais', []):
        linhas.append(f'▶️ {t["titulo"]}: {t["url"]}')
    return '\n'.join(l for l in linhas if l)


def proximos(evs, agora=None):
    agora = agora or time.time()
    return [e for e in evs if not e.get('inicio') or e['inicio'] + DEPOIS > agora]


def escolher(evs, arg):
    vivos = proximos(evs)
    if arg and arg.isdigit() and 1 <= int(arg) <= len(vivos):
        return vivos[int(arg) - 1]
    return vivos[-1] if vivos else None


# ---------------- download ----------------

def link_direto(url):
    """MediaFire: a página passa pelo FlareSolverr (desafio do Cloudflare) e o botão tem o link download*.mediafire."""
    if 'mediafire.com' not in url:
        return url, None
    corpo = json.dumps({'cmd': 'request.get', 'url': url, 'maxTimeout': 60000}).encode()
    req = urllib.request.Request(FLARESOLVERR, corpo, {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        h = (json.loads(r.read()).get('solution') or {}).get('response') or ''
    m = re.search(r'href="(https://download[^"]+)"', h)
    if not m:
        raise RuntimeError('o MediaFire não mostrou o botão de download (arquivo removido?)')
    nome = re.search(r'class="filename">([^<]+)', h)
    return m.group(1), (nome.group(1).strip() if nome else None)


def marcar(ev_id, texto):
    evs = ler_eventos()
    for e in evs:
        if e['id'] == ev_id:
            e['baixando'] = texto
    salvar(evs)


def set_campo(ev_id, campo, valor):
    evs = ler_eventos()
    for e in evs:
        if e['id'] == ev_id:
            e[campo] = valor
    salvar(evs)


def baixar(ev):
    """Baixa, extrai e põe em DVD/. Roda destacado (o bot não espera); avisa no WhatsApp no fim."""
    os.makedirs(BAIXANDO, exist_ok=True)
    pasta = os.path.join(BAIXANDO, str(ev['id']))
    os.makedirs(pasta, exist_ok=True)
    try:
        marcar(ev['id'], 'achando o link…')
        url, nome = link_direto(ev['link'])
        nome = os.path.basename(nome or urllib.request.unquote(url.split('?')[0].rsplit('/', 1)[-1]).replace('+', ' '))
        arq = os.path.join(pasta, nome)
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            total, feito, t = int(r.headers.get('Content-Length') or 0), 0, 0
            ja = os.path.exists(arq) and total and os.path.getsize(arq) == total   # tentativa anterior: só extrai
            livre = shutil.disk_usage(BAIXANDO).free
            if not ja and total and total * 3 > livre:   # rar + ISO extraído (o ISO costuma ser maior que o rar)
                raise RuntimeError(f'pouco espaço no 01TERA ({livre >> 30} GB livres)')
            f = None if ja else open(arq, 'wb')
            while f:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
                feito += len(bloco)
                if time.time() - t > 20:
                    t = time.time()
                    marcar(ev['id'], f'baixando {feito >> 20} de {total >> 20} MB' if total else f'baixando {feito >> 20} MB')
            if f:
                f.close()
        marcar(ev['id'], 'extraindo…')
        if nome.lower().endswith(('.rar', '.zip', '.7z')):
            # o 7z do Ubuntu (7zip "dfsg") não abre RAR: unrar oficial da RARLAB em ~/.local/bin (23/10/2026)
            if nome.lower().endswith('.rar') and os.path.exists(UNRAR):
                cmd = [UNRAR, 'x', '-o+', '-y', arq, pasta + '/']
            else:
                cmd = ['7z', 'x', '-y', '-o' + pasta, arq]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode:
                raise RuntimeError(os.path.basename(cmd[0]) + ': ' + ((p.stdout + p.stderr).strip().splitlines() or ['?'])[-1][:120])
            os.remove(arq)
        isos = [os.path.join(d, n) for d, _, ns in os.walk(pasta) for n in ns if n.lower().endswith('.iso')]
        if not isos:
            raise RuntimeError('não veio nenhum .iso dentro do arquivo')
        iso = max(isos, key=os.path.getsize)
        sys.path.insert(0, PASTA)
        from ra_hash import hash_ps2
        try:
            serial = hash_ps2(iso)[1]
        except Exception:
            serial = ''
        titulo = re.sub(r'[\\/:*?"<>|]', '', ev['jogo']).strip() or os.path.splitext(os.path.basename(iso))[0]
        final = f'{serial}.{titulo}.iso' if re.fullmatch(r'[A-Z]{4}_\d{3}\.\d{2}', serial or '') else f'{titulo}.iso'
        destino = os.path.join(JOGOS, 'DVD' if os.path.getsize(iso) > 700 * 1024 ** 2 else 'CD', final)
        shutil.move(iso, destino)
        shutil.rmtree(pasta, ignore_errors=True)
        marcar(ev['id'], '')
        log('baixado:', destino)
        whats(f'✅ *{ev["jogo"]}* pronto: {final} ({os.path.getsize(destino) >> 20} MB).\n'
              '🛒 Já aparece na Loja do PS2 (jogar pela nuvem ou ⬇ instalar no pendrive da TV box).')
        if ev.get('vmc') and not ev.get('kit'):   # anúncio veio com o memory card também (24/10/2026)
            kit_vmc(ev)
    except Exception as e:
        marcar(ev['id'], '')
        log('download falhou:', e)
        whats(f'❌ Não consegui baixar *{ev["jogo"]}*: {e}')


# ---------------- kit de VMC (memory card de rede) ----------------

KITS = f'http://{os.environ.get("PS2_KITS", "localhost")}:8792/kits/enviar'


def codigo_do_jogo(jogo, nomes=()):
    """Serial do ISO (SLUS_203.12) pela biblioteca ou pelo nome do arquivo baixado."""
    for _, n in no_acervo(jogo):
        m = re.match(r'^([A-Z]{4}_\d{3}\.\d{2})\.', n)
        if m:
            return m.group(1)
    for n in nomes:
        m = re.match(r'^([A-Z]{4}_\d{3}\.\d{2})', n)
        if m:
            return m.group(1)
    return ''


def kit_vmc(ev):
    """Baixa o VMC do anúncio, acha o memory card e manda como kit ao kits_servidor.py, já aprovado."""
    os.makedirs(BAIXANDO, exist_ok=True)
    pasta = os.path.join(BAIXANDO, f'{ev["id"]}-vmc')
    os.makedirs(pasta, exist_ok=True)
    try:
        marcar(ev['id'], 'baixando o VMC…')
        url, nome = link_direto(ev['vmc'])
        nome = os.path.basename(nome or urllib.request.unquote(url.split('?')[0].rsplit('/', 1)[-1]).replace('+', ' '))
        arq = os.path.join(pasta, nome)
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(arq, 'wb') as f:
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
        if nome.lower().endswith(('.rar', '.zip', '.7z')):
            marcar(ev['id'], 'extraindo o VMC…')
            cmd = ([UNRAR, 'x', '-o+', '-y', arq, pasta + '/'] if nome.lower().endswith('.rar') and os.path.exists(UNRAR)
                   else ['7z', 'x', '-y', '-o' + pasta, arq])
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode:
                raise RuntimeError('7z: ' + ((p.stdout + p.stderr).strip().splitlines() or ['?'])[-1][:120])
            os.remove(arq)
        vmcs = []
        for d, _, ns in os.walk(pasta):
            for n in ns:
                f = os.path.join(d, n)
                if os.path.getsize(f) <= 64 * 1024 ** 2:
                    with open(f, 'rb') as g:
                        if b'Sony PS2 Memory Card Format' in g.read(0x40):
                            vmcs.append(f)
        if not vmcs:
            raise RuntimeError('não achei nenhum memory card PS2 dentro do arquivo do VMC')
        vmc = max(vmcs, key=os.path.getsize)
        cod = codigo_do_jogo(ev['jogo'])
        if not cod:
            raise RuntimeError(f'"{ev["jogo"]}" não está na biblioteca: preciso do ISO para saber o serial '
                               '(/evento baixar resolve: o jogo baixado entra na biblioteca)')
        dados = {'codigo': cod, 'titulo': ev['jogo'], 'dns': (ev['dns'] or [''])[0], 'servidor': ev['servidor'],
                 'autor': 'bot do evento',
                 'notas': f'VMC chegou no anúncio do evento ({time.strftime("%d/%m/%Y %H:%M")}); DNS do evento embutido',
                 'arquivos': [{'nome': os.path.basename(vmc), 'dados': base64.b64encode(open(vmc, 'rb').read()).decode()}]}
        req = urllib.request.Request(KITS, json.dumps(dados).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read())
        if not resp.get('ok'):
            raise RuntimeError(resp.get('erro') or 'o servidor de kits recusou o VMC')
        marcar(ev['id'], 'aprovar…')
        p = subprocess.run([sys.executable, os.path.join(PASTA, 'kits_servidor.py'), 'aprovar', str(resp['numero'])],
                           capture_output=True, text=True)
        kit = os.path.basename((p.stdout or '').strip().split()[-1]) if p.returncode == 0 else ''
        if not kit:
            raise RuntimeError('o kit chegou ao servidor mas a aprovação falhou: ' + (p.stderr.strip() or '?')[:100])
        set_campo(ev['id'], 'kit', kit)
        shutil.rmtree(pasta, ignore_errors=True)
        log('kit VMC:', kit)
        whats('💾 VMC de *' + ev['jogo'] + '* pronto: kit *' + kit + '* aprovado.\n'
              '📦 Central da TV box → Kits → "' + ev['jogo'] + '" → aplicar: coloca o memory card no pendrive e '
              'o DNS do evento entra na TV box junto.')
    except Exception as e:
        marcar(ev['id'], '')
        log('kit VMC falhou:', e)
        whats(f'❌ O VMC de *{ev["jogo"]}* não ficou pronto: {e}')
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


# ---------------- vigia (cron */5) ----------------

def vigiar():
    evs, agora, mudou = ler_eventos(), time.time(), False
    for ev in proximos(evs, agora):
        falta = (ev.get('inicio') or 0) - agora
        if not ev.get('inicio'):
            continue
        if falta <= 2 * 3600 and not ev.get('conferido') and falta > -1800:
            ev['conferido'] = True
            mudou = True
            whats(conferencia(ev))
        if falta <= 15 * 60 and not ev.get('lembrado') and falta > -1800:
            ev['lembrado'] = True
            mudou = True
            whats(f'⏰ *{ev["jogo"]}* começa {hora(ev["inicio"])}!'
                  + (f'\n🖥️ Entre no servidor *{ev["servidor"]}*' if ev['servidor'] else ''))
    antigos = [e for e in evs if e.get('inicio') and e['inicio'] + 7 * 86400 < agora]
    if antigos or mudou:
        salvar([e for e in evs if e not in antigos])


def conferencia(ev):
    acervo = no_acervo(ev['jogo'])
    linhas = [f'🎮 *{ev["jogo"]}* {hora(ev["inicio"])} — conferência:']
    if acervo:
        linhas.append('💿 Jogo ✅ ' + acervo[0][1])
    elif ev.get('baixando'):
        linhas.append(f'💿 Jogo ⬇ {ev["baixando"]}')
    else:
        linhas.append('💿 Jogo ❌ não está na biblioteca' + (' (responda */evento baixar*)' if ev.get('link') else ''))
    for ip in ev['dns'] or []:
        ms = dns_responde(ip)
        linhas.append(f'🌐 DNS {ip} ✅ respondeu ({ms} ms)' if ms is not None else f'🌐 DNS {ip} ❌ não respondeu')
    b = estado_box()
    if b is None:
        linhas.append('📦 TV box: ➖ fora do alcance daqui (fora de casa?)')
    elif b.get('cabo'):
        linhas.append(f'📦 TV box ✅ PS2 no cabo da box ({b["cabo"]}): o DNS do evento entra sozinho às '
                      f'{dt.datetime.fromtimestamp(ev["inicio"] - ANTES, FUSO):%H:%M}')
    else:
        linhas.append('📦 TV box: PS2 não está no cabo da box — ponha o DNS do evento na rede do jogo')
    if ev['servidor']:
        linhas.append(f'🖥️ Servidor: *{ev["servidor"]}*')
    return '\n'.join(linhas)


# ---------------- comandos ----------------

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'lista'
    arg = sys.argv[2] if len(sys.argv) > 2 else ''
    evs = ler_eventos()
    if cmd in ('novo', 'ler'):
        ev = ler_anuncio(sys.stdin.read())
        if not ev['dns'] and not ev['link'] and not ev['inicio']:
            print('❓ Não entendi o anúncio. Mande */evento* seguido do texto inteiro (jogo, horário, DNS, link).')
            return
        if cmd == 'ler':
            return print(json.dumps(ev, ensure_ascii=False, indent=1))
        # o mesmo jogo no mesmo horário substitui o anterior (anúncio colado de novo, corrigido)
        evs = [e for e in evs if not (compacto(e['jogo']) == compacto(ev['jogo']) and e.get('inicio') == ev['inicio'])]
        ev['id'] = int(time.time())
        evs.append(ev)
        salvar(evs)
        log('novo evento:', ev['jogo'], ev['inicio'], ev['dns'])
        print('📅 Evento salvo!\n' + resumo(ev) + f'\n#{ev["id"]}')
    elif cmd == 'lista':
        vivos = proximos(evs)
        print('\n\n'.join(resumo(e, i + 1) for i, e in enumerate(vivos)) if vivos
              else 'Nenhum evento online marcado. Cole o anúncio com */evento* na frente.')
    elif cmd == 'cancelar':
        ev = escolher(evs, arg)
        if not ev:
            return print('Nenhum evento para cancelar.')
        salvar([e for e in evs if e['id'] != ev['id']])
        print(f'🗑️ Evento *{ev["jogo"]}* cancelado (o DNS da TV box volta ao normal em até 5 min).')
    elif cmd == 'baixar':
        ev = escolher(evs, arg)
        if not ev:
            return print('Nenhum evento marcado.')
        acervo = no_acervo(ev['jogo'])
        if acervo:
            return print(f'✅ *{ev["jogo"]}* já está aqui: {acervo[0][1]}')
        if not ev.get('link'):
            return print('O anúncio desse evento não tem link do jogo.')
        if ev.get('baixando'):
            return print(f'⬇ Já estou nisso: {ev["baixando"]}')
        marcar(ev['id'], 'começando…')
        subprocess.Popen([sys.executable, os.path.abspath(__file__), '_baixar', str(ev['id'])], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=open(LOG, 'a'))
        print(f'⬇ Baixando *{ev["jogo"]}*… aviso aqui quando estiver pronto. Andamento: */evento*')
    elif cmd == '_baixar':
        ev = next((e for e in evs if str(e['id']) == arg), None)
        if ev:
            baixar(ev)
    elif cmd == 'vmc':
        ev = escolher(evs, arg)
        if not ev:
            return print('Nenhum evento marcado.')
        if not ev.get('vmc'):
            return print(f'O anúncio de *{ev["jogo"]}* não veio com link de VMC.')
        if ev.get('kit'):
            return print(f'✅ O VMC de *{ev["jogo"]}* já está pronto: kit *{ev["kit"]}*')
        if ev.get('baixando'):
            return print(f'⬇ Já estou nisso: {ev["baixando"]}')
        marcar(ev['id'], 'baixando o VMC…')
        subprocess.Popen([sys.executable, os.path.abspath(__file__), '_vmc', str(ev['id'])], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=open(LOG, 'a'))
        print(f'💾 Baixando o VMC de *{ev["jogo"]}*… avisa aqui quando estiver pronto.')
    elif cmd == '_vmc':
        ev = next((e for e in evs if str(e['id']) == arg), None)
        if ev:
            kit_vmc(ev)
    elif cmd == 'vigiar':
        vigiar()
    elif cmd == 'publico':   # o que a TV box recebe (videos_https /eventos)
        print(json.dumps([{k: e.get(k) for k in ('id', 'jogo', 'inicio', 'dns', 'servidor', 'tutoriais', 'vmc', 'kit')}
                          | {'antes': ANTES, 'depois': DEPOIS} for e in proximos(evs)], ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
