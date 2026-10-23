#!/usr/bin/env python3
"""Vídeos do PS2 na TV box (pedido do usuário 17/10/2026): lista de vídeos já no formato do player do navegador
(<id>.m2v MPEG-2 640x400 + <id>.pcm PCM 16 bits estéreo 22050 Hz + <id>.fim + <id>.json {"titulo"}), sem conversão.
Página inicial do navegador na box (porta 8780): botões Loja e Vídeos; tocar = manda "video <id>" ao
navegador_servidor (porta 8772), que pede ao PS2 host:video/<id>.m2v/.pcm (servidos pelo servidor_host.py).
Vídeos só os de ps2/video/ (na box). O vídeo do notebook por HTTPS foi retirado em 22/10/2026 (travava demais).
Loja (/loja/...): a página, o catálogo e as capas vêm do notebook (videos_https.py /loja, rede local ou HTTPS, com
a chave); as ações de SNES rodam AQUI (baixa a ROM do notebook se faltar e manda o navegador gravar no pendrive do
PS2 / jogar); as de jogos de PS2 (ISO na TV box de casa) só funcionam com o notebook na mesma rede.
Uso: videos.py [porta]
"""
import html, json, os, re, socket, sys, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASTA = os.path.dirname(os.path.abspath(__file__))
VIDEOS = os.path.join(PASTA, 'ps2', 'video')
LOJA = '/loja/loja.html'
# o Cloudflare (Browser Integrity Check) barra o "Python-urllib" com erro 1010: nome próprio nos pedidos (18/10/2026)
UA = 'ps2nav/1.0'
SNES = os.path.join(PASTA, 'ps2', 'snes')
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8780

ESTILO = """<style>
body{margin:0;width:640px;height:448px;overflow:hidden;background:#0b1630;color:#fff;font:20px sans-serif}
h1{margin:14px 20px;font-size:28px} .lista{margin:0 20px;height:360px;overflow-y:auto}
a.b{display:block;margin:0 0 12px;padding:14px 18px;background:#1d3b78;border-radius:12px;color:#fff;
text-decoration:none;font-size:22px} a.b:hover{background:#3466c8} .p{color:#9fb4e0;font-size:16px}
.grande{font-size:30px;padding:30px} .msg{margin:10px 20px;color:#ffd166}
</style>"""


def lista():
    vs = []
    for nome in sorted(os.listdir(VIDEOS)) if os.path.isdir(VIDEOS) else []:
        if nome.endswith('.m2v') and os.path.exists(os.path.join(VIDEOS, nome[:-4] + '.pcm')):
            vid = nome[:-4]
            try:
                titulo = json.load(open(os.path.join(VIDEOS, vid + '.json')))['titulo']
            except Exception:
                titulo = vid
            mb = (os.path.getsize(os.path.join(VIDEOS, nome)) + os.path.getsize(os.path.join(VIDEOS, vid + '.pcm'))) >> 20
            vs.append({'id': vid, 'titulo': titulo, 'mb': mb})
    return vs


def cfg():
    try:
        return json.load(open(os.path.join(PASTA, 'remoto.json')))
    except (OSError, ValueError):
        return {}


_url_boa = ['']


def remoto(caminho, timeout=15):
    """GET no videos_https.py do notebook (o último endereço que funcionou primeiro). Devolve (status, tipo, dados)."""
    c = cfg()
    urls = c.get('urls', [])
    urls = sorted(urls, key=lambda u: u != _url_boa[0])
    erro = None
    for url in urls:
        try:
            req = urllib.request.Request(url.rstrip('/') + caminho, headers={'X-Chave': c.get('chave', ''), 'User-Agent': UA})
            curto = url.startswith('http:') and url != _url_boa[0]   # rede local ainda não testada: desiste logo
            with urllib.request.urlopen(req, timeout=3 if curto else timeout) as r:
                _url_boa[0] = url
                return r.status, r.headers.get('Content-Type', ''), r.read()
        except urllib.error.HTTPError as e:
            return e.code, 'application/json', e.read()
        except Exception as e:
            erro = e
    return 502, 'application/json', json.dumps({'erro': f'servidor em nuvem fora do alcance ({erro})'}).encode()


def navegador(pedido):
    try:
        with socket.create_connection(('127.0.0.1', 8772), timeout=5) as c:
            c.sendall((pedido + '\n').encode())
            return c.makefile().readline().strip()
    except OSError as e:
        return f'navegador fora do ar ({e})'


# ---------- 🏆 Conquistas (23/10/2026): página montada aqui com os dados do app xeRAbora desta box ----------
XERABORA = 'http://127.0.0.1:18280'
INDICE_RA = os.path.join(PASTA, 'ps2', 'ra', 'indice.json')   # jogos preparados: serial → título, total, id no RA
BADGE = '/conquistas/medalha/'   # servidas daqui (cache em ps2/ra/medalhas), vindas do site do RetroAchievements
BADGE_ORIGEM = 'https://media.retroachievements.org/Badge/'
PASTA_MEDALHAS = os.path.join(PASTA, 'ps2', 'ra', 'medalhas')


def medalha(nome):
    """PNG da medalha ("609317" ou "609317_lock"), baixado uma vez e guardado; None se não der."""
    if not re.fullmatch(r'\d{1,9}(_lock)?', nome):
        return None
    arq = os.path.join(PASTA_MEDALHAS, nome + '.png')
    if not os.path.exists(arq):
        try:
            req = urllib.request.Request(BADGE_ORIGEM + nome + '.png', headers={'User-Agent': 'PS2-Henbox'})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = r.read()
        except Exception:
            return None
        os.makedirs(PASTA_MEDALHAS, exist_ok=True)
        with open(arq + '.tmp', 'wb') as f:
            f.write(d)
        os.replace(arq + '.tmp', arq)
    return open(arq, 'rb').read()


def xera(caminho):
    try:
        with urllib.request.urlopen(XERABORA + caminho, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return None


def indice_ra():
    try:
        return json.load(open(INDICE_RA, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def registrar_preparado(serial, titulo, iso):
    """Depois do preparar: guarda o jogo no índice da página de conquistas, com o id dele no RetroAchievements
    (pelo hash do ISO, a mesma consulta "gameid" que os emuladores fazem) e os dados do app xeRAbora."""
    from ra_hash import hash_ps2
    ind = indice_ra()
    item = ind.get(serial, {})
    nome, _, resto = titulo.partition(' — ')
    item.update({'titulo': nome, 'quando': time.strftime('%d/%m/%Y')})
    try:
        h = hash_ps2(iso)[0]
        req = urllib.request.Request(f'https://retroachievements.org/dorequest.php?r=gameid&m={h}',
                                     headers={'User-Agent': 'PS2-Henbox/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            jid = json.loads(r.read()).get('GameID')
        if jid:
            g = xera(f'/game?id={int(jid)}') or {}
            item.update({'id': int(jid), 'hash': h, 'nome': g.get('title') or nome,
                         'total': g.get('total') or len(g.get('achievements') or [])})
    except Exception:
        pass
    item.pop('sem', None)
    ind[serial] = item
    salvar_indice(ind)


def salvar_indice(ind):
    os.makedirs(os.path.dirname(INDICE_RA), exist_ok=True)
    with open(INDICE_RA + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(ind, f, ensure_ascii=False, indent=1)
    os.replace(INDICE_RA + '.tmp', INDICE_RA)


REVER_SEM_CONQUISTAS = 7 * 86400   # ISO que o RetroAchievements não reconheceu: tenta de novo uma vez por semana


def varrer_conquistas():
    """Prepara sozinho as conquistas dos ISOs do pendrive desta box que ainda não estão no índice (ISO instalado
    pela loja, copiado à mão…): hash, lista do xeRAbora em ps2/ra/<serial>.wl e o jogo na página 🏆. Não depende
    do PS2 ligado; a lista vai para o pendrive do PS2 no "Copiar para o PS2". Pula enquanto um jogo transmite
    (preparar troca o jogo que o app xeRAbora está servindo)."""
    from ra_hash import hash_ps2
    from ra_preparar import preparar
    pasta = os.path.realpath(os.path.join(PASTA, 'ps2', 'jogos-box'))
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith('.iso'):
            continue
        console = (xera('/state') or {}).get('console') or {}
        if console.get('connected') and console.get('frames'):
            return
        iso = os.path.join(pasta, nome)
        try:
            serial = hash_ps2(iso)[1]
        except Exception:
            continue
        e = indice_ra().get(serial) or {}
        if e.get('id') or (e.get('sem') and time.time() - e.get('t', 0) < REVER_SEM_CONQUISTAS):
            continue
        try:
            _, titulo = preparar(iso, serial, os.path.join(PASTA, 'ps2', 'ra'), log=lambda *a: None)
            registrar_preparado(serial, titulo, iso)
            print(f'conquistas preparadas sozinhas: {nome} → {titulo}', flush=True)
        except Exception as ex:
            ind = indice_ra()
            ind[serial] = {'titulo': nome, 'sem': str(ex)[:160], 't': time.time()}
            salvar_indice(ind)


DESBLOQUEIOS = os.path.join(PASTA, 'ps2', 'ra', 'desbloqueios.json')   # histórico: Xoom e navegador avisam


def ler_desbloqueios():
    try:
        return json.load(open(DESBLOQUEIOS, encoding='utf-8'))
    except (OSError, ValueError):
        return []


def vigiar_desbloqueios():
    """A cada 3 s: desbloqueio novo no xeRAbora (/state.unlocks, os 16 últimos da sessão) entra no histórico com a
    descrição e o jogo. O assistente do Xoom (pop-up com som) e o navegador (resumo ao voltar) leem daqui."""
    while True:
        try:
            st = xera('/state') or {}
            novos = [u for u in (st.get('unlocks') or []) if u.get('id')]
            if novos:
                hist = ler_desbloqueios()
                vistos = {d['id'] for d in hist}
                g = st.get('game') or {}
                desc = {a.get('id'): a.get('description') for a in (g.get('achievements') or [])}
                mudou = False
                for u in reversed(novos):   # do mais antigo ao mais novo
                    if u['id'] in vistos:
                        continue
                    hist.append({'id': u['id'], 'titulo': u.get('title'), 'medalha': str(u.get('badge') or ''),
                                 'pontos': u.get('points', 0), 'descricao': desc.get(u['id']) or '',
                                 'jogo': g.get('title') or '', 'quando': time.time() - (u.get('ago') or 0),
                                 'navegador': False})
                    mudou = True
                if mudou:
                    hist = hist[-300:]
                    with open(DESBLOQUEIOS + '.tmp', 'w', encoding='utf-8') as f:
                        json.dump(hist, f, ensure_ascii=False, indent=1)
                    os.replace(DESBLOQUEIOS + '.tmp', DESBLOQUEIOS)
        except Exception as e:
            print('vigia de desbloqueios:', e, flush=True)
        time.sleep(3)


def laco_conquistas():
    time.sleep(60)
    while True:
        try:
            varrer_conquistas()
        except Exception as e:
            print('varredura de conquistas:', e, flush=True)
        time.sleep(30 * 60)


ESTILO_RA = ('<style>.topo{margin:6px 20px 10px;color:#9fb4e0;font-size:16px} .topo b{color:#ffd166}'
             '.c{display:flex;align-items:center;gap:12px;margin:0 0 10px;padding:8px 12px;background:#132a57;'
             'border-radius:10px} .c img{width:48px;height:48px;border-radius:6px;flex:none} .c .t{font-size:18px}'
             '.c .d{color:#9fb4e0;font-size:14px} .c.ganha{background:#3a3010} .c.ganha .t{color:#ffd166}'
             '.barra{height:8px;background:#0b1630;border-radius:4px;margin-top:6px;overflow:hidden}'
             '.barra i{display:block;height:100%;background:#ffd166}</style>')


def pagina_no_ps2(msg=''):
    """💾 Jogos no pendrive do PS2 (ps2/no-ps2.json, anotados pelo navegador_servidor nas cópias) com ▶ Jogar direto."""
    try:
        jogos = json.load(open(os.path.join(PASTA, 'ps2', 'no-ps2.json'), encoding='utf-8'))
    except (OSError, ValueError):
        jogos = {}
    ind, itens = indice_ra(), ''
    for arq in sorted(jogos, key=lambda a: a[12:].lower() if re.match(r'^[A-Z]{4}_\d{3}\.\d{2}\.', a) else a.lower()):
        serial = arq[:11] if re.match(r'^[A-Z]{4}_\d{3}\.\d{2}\.', arq) else ''
        nome = os.path.splitext(arq[12:] if serial else arq)[0]
        ra = ind.get(serial) or {}
        tag = f'🏆 {ra.get("total", "")} conquistas · ' if ra.get('id') else ''
        itens += (f'<a class="b" href="/no-ps2/jogar?arquivo={urllib.parse.quote(arq)}">▶ {html.escape(nome)}'
                  f'<div class="p">{tag}{html.escape(serial or "sem código")} · copiado em {html.escape(jogos[arq].get("quando", ""))}</div></a>')
    if not itens:
        itens = '<div class="msg">Nenhum jogo copiado ainda. Na Loja, use ⬇ Copiar para o PS2.</div>'
    aviso = f'<div class="msg">{html.escape(msg)}</div>' if msg else ''
    return '<h1>💾 No pendrive do PS2</h1>' + aviso + '<div class="lista"><a class="b" href="/">← Voltar</a>' + itens + '</div>'


def ao_vivo():
    """Com um jogo transmitindo para o xeRAbora, as páginas 🏆 se recarregam sozinhas (acompanhar pela TV)."""
    c = ((xera('/state') or {}).get('console') or {})
    return '<meta http-equiv="refresh" content="15">' if c.get('connected') and c.get('frames') else ''


def pagina_conquistas():
    perfil, st = xera('/profile'), xera('/state')
    if perfil is None or st is None:
        return ('<h1>🏆 Conquistas</h1><div class="msg">O app xeRAbora não está respondendo nesta TV box.</div>'
                '<div class="lista"><a class="b" href="/">← Voltar</a></div>')
    topo = (f'<div class="topo">👤 {html.escape(perfil.get("user") or "?")} · <b>{perfil.get("points", 0)} pontos</b>'
            + (f' · {html.escape(perfil["presence"])}' if perfil.get('presence') else '') + '</div>')
    itens, vistos = '', set()
    for u in ler_desbloqueios()[-5:][::-1]:   # desbloqueadas recentemente (histórico do vigia)
        quando = time.strftime('%d/%m %H:%M', time.localtime(u.get('quando') or 0))
        itens += (f'<div class="c ganha"><img src="{BADGE}{html.escape(u.get("medalha", ""))}.png">'
                  f'<div><div class="t">🏆 {html.escape(u.get("titulo") or "")} · {u.get("pontos", 0)} pts</div>'
                  f'<div class="d">{html.escape(u.get("jogo") or "")} · {quando}</div></div></div>')
    jogos = []
    g = st.get('game') or {}
    if g.get('id'):
        conq = g.get('achievements') or []
        ganhas = sum(1 for a in conq if str(a.get('state', '')).lower() in ('unlocked', 'earned', 'won'))
        jogos.append((g['id'], g.get('title'), ganhas, len(conq), '▶ jogando agora' if (st.get('console') or {}).get('frames') else 'último jogo identificado'))
    for j in ((xera('/library') or {}).get('games') or []):
        jid = j.get('id') or j.get('game_id')
        if jid:
            jogos.append((jid, j.get('title'), j.get('awarded') or j.get('earned') or 0, j.get('total') or 0, 'na sua biblioteca'))
    for serial, j in sorted(indice_ra().items(), key=lambda x: x[1].get('titulo', '')):
        if j.get('id'):
            jogos.append((j['id'], j.get('nome') or j.get('titulo'), None, j.get('total') or 0, f'preparado no PS2 · {serial}'))
    for jid, titulo, ganhas, total, onde in jogos:
        if jid in vistos:
            continue
        vistos.add(jid)
        pct = int(100 * (ganhas or 0) / total) if total and ganhas is not None else 0
        info = f'{ganhas} de {total} conquistas' if ganhas is not None else f'{total} conquistas'
        itens += (f'<a class="b" href="/conquistas/jogo?id={int(jid)}">{html.escape(titulo or "?")}'
                  f'<div class="p">{info} · {html.escape(onde)}</div><div class="barra"><i style="width:{pct}%"></i></div></a>')
    if not jogos:
        itens += '<div class="msg">Nenhum jogo ainda. Na Loja, use 🏆 Preparar conquistas num jogo.</div>'
    return (ao_vivo() + '<h1>🏆 Conquistas</h1>' + ESTILO_RA + topo + '<div class="lista"><a class="b" href="/">← Voltar</a>'
            + itens + '</div>')


def pagina_jogo_ra(jid):
    g = xera(f'/game?id={int(jid)}')
    if not g:
        return '<h1>🏆</h1><div class="msg">Não consegui ler esse jogo.</div><a class="b" href="/conquistas">← Voltar</a>'
    conq = sorted(g.get('achievements') or [], key=lambda a: (not a.get('earned'), a.get('order') or 0))
    itens = ''
    for a in conq:
        ganha = bool(a.get('earned'))
        img = f'{BADGE}{html.escape(str(a.get("badge", "")))}{"" if ganha else "_lock"}.png'
        quando = f' · {html.escape(str(a["earned"])[:10])}' if ganha else ''
        itens += (f'<div class="c{" ganha" if ganha else ""}"><img src="{img}"><div>'
                  f'<div class="t">{html.escape(a.get("title") or "")} · {a.get("points", 0)} pts</div>'
                  f'<div class="d">{html.escape(a.get("description") or "")}{quando}</div></div></div>')
    topo = f'<div class="topo"><b>{g.get("awarded", 0)} de {g.get("total", len(conq))}</b> desbloqueadas</div>'
    return (ao_vivo() + f'<h1>{html.escape(g.get("title") or "🏆")}</h1>' + ESTILO_RA + topo
            + '<div class="lista"><a class="b" href="/conquistas">← Voltar</a>' + itens + '</div>')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def pagina(self, corpo):
        d = f'<!doctype html><meta charset="utf-8"><title>PS2</title>{ESTILO}{corpo}'.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def json(self, obj, codigo=200):
        d = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def loja_snes(self):
        """Lista de ROMs do notebook + o andamento dos pedidos DESTE navegador (não o da TV box de casa)."""
        st, _, d = remoto('/loja/api/loja/snes')
        if st != 200:
            return self.json({'roms': [], 'retroarch': {}, 'navegador': False, 'erro': d.decode(errors='ignore')})
        lista_ = json.loads(d)
        try:
            estado = json.loads(navegador('pedido') or '{}')
        except ValueError:
            estado = {}
        atual, res = estado.get('atual') or {}, estado.get('resultados') or {}
        def ped(nome):
            if atual.get('arquivo') == nome:
                return {'fase': atual.get('fase'), 'estado': atual.get('estado') or 'na fila',
                        'pct': atual.get('pct', 0), 'andamento': True}
            return res.get(nome, {})
        for r in lista_.get('roms', []):
            r['pedido'] = ped(r['arquivo'])
        ra = lista_.get('retroarch') or {}
        ra['pedido'], ra['na_tvbox'] = ped('__retroarch__'), False
        lista_['retroarch'] = ra
        lista_['navegador'] = navegador('status') == 'aberto'
        return self.json(lista_)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            corpo = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
        except ValueError:
            corpo = {}
        acao = u.path[len('/loja/'):] if u.path.startswith('/loja/') else ''
        arq = os.path.basename(str(corpo.get('arquivo', '')))
        if acao == 'api/loja/snes/retroarch':
            r = navegador('retroarch')
            return self.json({'ok': r == 'ok', 'msg': 'Instalando o SNESticle no pendrive do PS2…' if r == 'ok' else r})
        if acao in ('api/loja/snes', 'api/loja/snes/jogar'):
            if not arq.lower().endswith(('.smc', '.sfc')):
                return self.json({'ok': False, 'msg': 'ROM inválida'}, 400)
            if acao.endswith('/jogar'):
                r = navegador('jogar ' + arq)
                return self.json({'ok': r == 'ok', 'msg': 'Abrindo no PS2…' if r == 'ok' else r})
            if not os.path.isfile(os.path.join(SNES, arq)):   # baixa do notebook antes de gravar no PS2
                st, _, d = remoto('/rom/' + urllib.parse.quote(arq), timeout=60)
                if st != 200:
                    return self.json({'ok': False, 'msg': 'não consegui baixar a ROM do servidor em nuvem'})
                os.makedirs(SNES, exist_ok=True)
                with open(os.path.join(SNES, arq + '.tmp'), 'wb') as f:
                    f.write(d)
                os.replace(os.path.join(SNES, arq + '.tmp'), os.path.join(SNES, arq))
            r = navegador('copiar ' + arq)
            return self.json({'ok': r == 'ok', 'msg': 'Gravando no pendrive do PS2…' if r == 'ok' else r})
        if acao == 'api/jogar':   # jogo de PS2 pela rede: Neutrino do pendrive + udpfs_nuvem.py desta box
            st, _, d = remoto('/loja/api/loja')
            jogo = next((j for j in (json.loads(d).get('jogos', []) if st == 200 else [])
                         if j.get('id') == corpo.get('id')), None)
            if not jogo:
                return self.json({'ok': False, 'msg': 'jogo não encontrado no catálogo'})
            r = navegador('neutrino ' + jogo['arquivo'])
            return self.json({'ok': r == 'ok', 'msg': f'Abrindo {jogo["nome"]} no PS2 (jogo em nuvem)…' if r == 'ok' else r})
        if acao in ('api/jogar-ra', 'api/menu-ra', 'api/copiar-ra', 'api/preparar-ra'):
            # 🏆 conquistas (xeRAbora, 23/10/2026): OPL-RA-SMB.ELF (~/ps2-monitor/opl-ra) abre o jogo direto e manda a
            # memória dele ao app xeRAbora desta box. Pelo Samba o xeRAbora ainda não funciona (rede disputada, tela
            # preta), então o jogo vai para o pendrive do PRÓPRIO PS2 (copiar-ra, mass:/DVD) e abre de lá ("bdm").
            # preparar-ra faz aqui o "RA: check game support" (ra_preparar.py: hash do ISO + lista do app xeRAbora) e
            # manda o .wl para mass:/RA/ no pendrive do PS2; copiar-ra prepara antes de copiar o ISO. menu-ra (menu do
            # OPL-RA) fica para checar à mão.
            elf = 'host:oplra/OPL-RA-SMB.ELF'
            if acao == 'api/menu-ra':
                r = navegador(f'abrir {elf}')
                return self.json({'ok': r == 'ok', 'msg': 'Abrindo o OPL com conquistas no PS2…' if r == 'ok' else r})
            st, _, d = remoto('/loja/api/loja')
            jogo = next((j for j in (json.loads(d).get('jogos', []) if st == 200 else [])
                         if j.get('id') == corpo.get('id')), None)
            if not jogo or not jogo.get('instalado'):
                return self.json({'ok': False, 'msg': 'só jogos instalados no pendrive da TV box'})
            if acao in ('api/preparar-ra', 'api/copiar-ra'):
                from ra_preparar import preparar
                iso = os.path.join(os.path.realpath(os.path.join(PASTA, 'ps2', 'jogos-box')), jogo['arquivo'])
                try:
                    _, titulo = preparar(iso, jogo['id'], os.path.join(PASTA, 'ps2', 'ra'))
                except Exception as e:
                    return self.json({'ok': False, 'msg': f'Sem conquistas: {e}'})
                try:
                    registrar_preparado(jogo['id'], titulo, iso)
                except Exception:
                    pass
                r = navegador(f"copiar2 host:ra/{jogo['id']}.wl|mass:/RA/{jogo['id']}.wl|ra-wl:{jogo['id']}")
                if r != 'ok':
                    if acao == 'api/preparar-ra':   # vai para o pendrive do PS2 no "Copiar para o PS2"
                        return self.json({'ok': True, 'msg': f'🏆 {titulo} — preparado (o PS2 recebe ao copiar o jogo)'})
                    return self.json({'ok': False, 'msg': r})
                if acao == 'api/preparar-ra':
                    return self.json({'ok': True, 'msg': f'🏆 {titulo} — conquistas preparadas no pendrive do PS2'})
            if acao == 'api/copiar-ra':   # USB 1.1 do PS2: ~1 MB/s; o progresso aparece na tela do navegador
                if jogo['tamanho'] >= 4 * 1024 ** 3:
                    return self.json({'ok': False, 'msg': 'maior que 4 GB: não cabe no pendrive FAT32 do PS2'})
                r = navegador(f"copiar2 host:jogos-box/{jogo['arquivo']}|mass:/DVD/{jogo['arquivo']}|ra:{jogo['id']}")
                return self.json({'ok': r == 'ok', 'msg': f'Copiando {jogo["nome"]} para o pendrive do PS2 '
                                  f'(~{jogo["tamanho"] // 1048576 // 60 + 1} min)…' if r == 'ok' else r})
            args = f"{jogo['arquivo']}|{jogo['id']}|DVD|bdm"
            if len(args.encode()) > 127:
                return self.json({'ok': False, 'msg': 'nome do arquivo longo demais para o pedido ao PS2'})
            r = navegador(f'abrir {elf}|{args}')
            return self.json({'ok': r == 'ok', 'msg': f'Abrindo {jogo["nome"]} com conquistas…' if r == 'ok' else r})
        # jogos de PS2 (ISO para a TV box de casa) e RetroArch na TV box: só com o notebook na mesma rede
        casa = cfg().get('casa')
        if casa and acao.startswith('api/'):
            try:
                req = urllib.request.Request(casa.rstrip('/') + '/' + acao, data=json.dumps(corpo).encode(),
                                             headers={'Content-Type': 'application/json', 'User-Agent': UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    return self.json(json.loads(r.read()))
            except Exception:
                pass
        return self.json({'ok': False, 'msg': 'Disponível só em casa (com o servidor em nuvem na mesma rede).'})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == '/loja/api/loja/snes':
            return self.loja_snes()
        if u.path == '/api/ps2/temperatura':   # temperatura.js da loja pede pela raiz do site
            u = u._replace(path='/loja/api/ps2/temperatura')
        if u.path.startswith('/loja/'):
            st, tipo, d = remoto(u.path + (('?' + u.query) if u.query else ''))
            self.send_response(st)
            self.send_header('Content-Type', tipo or 'application/octet-stream')
            self.send_header('Content-Length', str(len(d)))
            self.end_headers()
            self.wfile.write(d)
            return
        q = urllib.parse.parse_qs(u.query)
        if u.path == '/':
            self.pagina(f'<h1>PS2</h1><div class="lista"><a class="b grande" href="{html.escape(LOJA)}">🛒 Loja</a>'
                        '<a class="b grande" href="/videos">🎬 Vídeos</a>'
                        '<a class="b grande" href="/no-ps2">💾 No pendrive do PS2</a>'
                        '<a class="b grande" href="/conquistas">🏆 Conquistas</a></div>')
        elif u.path == '/no-ps2':
            self.pagina(pagina_no_ps2())
        elif u.path == '/no-ps2/jogar':
            arq = os.path.basename((q.get('arquivo') or [''])[0])
            try:
                registrados = json.load(open(os.path.join(PASTA, 'ps2', 'no-ps2.json'), encoding='utf-8'))
            except (OSError, ValueError):
                registrados = {}
            if arq not in registrados:
                return self.pagina(pagina_no_ps2('Esse jogo não está na lista do pendrive do PS2.'))
            serial = arq[:11] if re.match(r'^[A-Z]{4}_\d{3}\.\d{2}\.', arq) else 'SLUS_000.00'
            # OPL-RA pelo pendrive do PS2 ("bdm"): com a lista RA/<serial>.wl tem conquistas, sem ela abre normal
            r = navegador(f'abrir host:oplra/OPL-RA-SMB.ELF|{arq}|{serial}|DVD|bdm')
            self.pagina(pagina_no_ps2('Abrindo no PS2…' if r == 'ok' else r))
        elif u.path == '/conquistas':
            self.pagina(pagina_conquistas())
        elif u.path.startswith('/conquistas/medalha/') and u.path.endswith('.png'):
            d = medalha(u.path[len('/conquistas/medalha/'):-4])
            if d is None:
                return self.send_error(404)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'max-age=604800')
            self.send_header('Content-Length', str(len(d)))
            self.end_headers()
            self.wfile.write(d)
        elif u.path == '/henbox':   # identificação para o app do celular achar esta TV box sozinho na rede
            return self.json({'app': 'ps2-henbox', 'conquistas': True, 'estado': True})
        elif u.path in ('/estado', '/estado.json'):   # lista de conferência da instalação (configurar.checklist)
            import configurar
            itens = configurar.checklist()
            if u.path.endswith('.json'):
                return self.json(itens)
            sinal = {True: '✅', False: '❌', None: '➖'}
            linhas = ''.join(f'<div class="b"><b>{sinal[i["ok"]]} {html.escape(i["item"])}</b>'
                             f'<div class="p">{html.escape(i["detalhe"])}</div>'
                             + (f'<div class="p">👉 {html.escape(i["resolver"])}</div>' if i['resolver'] else '') + '</div>'
                             for i in itens)
            self.pagina('<meta http-equiv="refresh" content="20"><h1>🩺 Estado do PS2 Henbox</h1><div class="lista">'
                        + linhas + '<a class="b" href="/">← Voltar</a></div>')
        elif u.path == '/conquistas/api/desbloqueios':   # ?desde=<epoch>: o assistente do Xoom faz o pop-up
            try:
                desde = float((q.get('desde') or ['0'])[0])
            except ValueError:
                desde = 0
            return self.json([{k: v for k, v in d.items() if k != 'navegador'}
                              for d in ler_desbloqueios() if (d.get('quando') or 0) > desde])
        elif u.path == '/conquistas/jogo':
            try:
                self.pagina(pagina_jogo_ra(int((q.get('id') or ['0'])[0])))
            except ValueError:
                self.send_error(404)
        elif u.path == '/videos':
            itens = ''.join(f'<a class="b" href="/tocar?id={urllib.parse.quote(v["id"])}">{html.escape(v["titulo"])}'
                            f'<div class="p">{v["mb"]} MB · na TV box</div></a>' for v in lista())
            self.pagina('<h1>🎬 Vídeos</h1><div class="lista"><a class="b" href="/">← Voltar</a>'
                        + (itens or '<div class="msg">Nenhum vídeo em ps2/video na TV box.</div>') + '</div>')
        elif u.path == '/tocar':
            vid = (q.get('id') or [''])[0]
            validos = {v['id'] for v in lista()}
            if vid not in validos:
                return self.pagina('<div class="msg">Vídeo não encontrado.</div><a class="b" href="/videos">← Voltar</a>')
            r = navegador(f'video {vid}')
            self.pagina(f'<h1>🎬 Abrindo…</h1><div class="msg">{html.escape(r)}</div>'
                        '<div class="lista"><a class="b" href="/videos">← Voltar à lista</a></div>')
        else:
            self.send_error(404)


PORTA_ACHAR = 8779   # UDP: "HENBOX?" → {"app": "ps2-henbox", "porta": 8780}; os apps acham a box na hora (broadcast)


def responder_busca():
    import socket
    so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    so.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    so.bind(('0.0.0.0', PORTA_ACHAR))
    resposta = json.dumps({'app': 'ps2-henbox', 'porta': PORTA}).encode()
    while True:
        try:
            dados, quem = so.recvfrom(64)
            if dados.startswith(b'HENBOX?'):
                so.sendto(resposta, quem)
        except OSError:
            time.sleep(1)


if __name__ == '__main__':
    print(f'vídeos do PS2 em http://0.0.0.0:{PORTA}/ ({VIDEOS})', flush=True)
    import threading
    threading.Thread(target=responder_busca, daemon=True).start()
    threading.Thread(target=laco_conquistas, daemon=True).start()   # 🏆 prepara sozinho os ISOs novos
    threading.Thread(target=vigiar_desbloqueios, daemon=True).start()   # 🏆 histórico de desbloqueios
    ThreadingHTTPServer(('0.0.0.0', PORTA), H).serve_forever()
