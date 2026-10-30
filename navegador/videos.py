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
import html, json, os, re, shlex, shutil, socket, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
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


# ---------- 🗄 Cache da loja (25/10/2026): a loja inteira de olhar NO notebook desligado ----------
# Um difusor a cada 5 min copia para cache-loja/ a página, temperatura.js, api/loja, api/loja/snes e todas as capas
# que aparecem no catálogo. Quando o notebook não responde (remoto → 502), o servidor de /loja/* cai aqui e serve
# o cache: a loja continua navendo (instalar, baixar e ficha de jogo precisam do notebook — a capa da tela avisa).
CACHE_LOJA = os.path.join(PASTA, 'cache-loja')
_cache = {}   # nome do arquivo → (mtime, tamanho) na última passada (evita regravar igual)


def cache_log(*a):
    print(time.strftime('%d/%m %H:%M:%S'), 'cache da loja:', *a, flush=True)


def cache_salvar(nome, dados):
    os.makedirs(os.path.dirname(os.path.join(CACHE_LOJA, nome)), exist_ok=True)
    arq = os.path.join(CACHE_LOJA, nome)
    st = os.stat(arq) if os.path.exists(arq) else None
    if st and st.st_size == len(dados) and st.st_mtime > time.time() - 2:
        return   # igual ao que já há: não regrava (e não empurra dif inútil)
    with open(arq + '.tmp', 'wb') as f:
        f.write(dados)
    os.replace(arq + '.tmp', arq)
    cache_log(nome, f'{len(dados) >> 10} KB')


def cache_meta():
    try:
        return json.load(open(os.path.join(CACHE_LOJA, 'meta.json'), encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def cache_capas_do_json(obj, limite=60):
    """Todo 'capa': 'capas/…' (fronteando dicionários e listas do catálogo) que o cache ainda não tem.
    Devolve quantas baixou (o limite protege o ciclo de uma varredura enorme do notebook)."""
    faltou = 0
    cont = {'vista': 0, 'tinha': 0, 'baixou': 0, 'erro': 0}
    pilha = [obj]
    while pilha and faltou < limite:
        o = pilha.pop()
        if isinstance(o, dict):
            c = o.get('capa')
            if isinstance(c, str) and c.startswith('capas/') and '..' not in c:
                cont['vista'] += 1
                nome = c[len('capas/'):]
                if not os.path.exists(os.path.join(CACHE_LOJA, 'capas', nome)):
                    st, _, d = remoto('/loja/' + urllib.parse.quote(c), 15)
                    if st == 200 and d:
                        cache_salvar('capas/' + nome, d)
                        cont['baixou'] += 1
                        faltou += 1
                    else:
                        cont['erro'] += 1
                        cache_log('capa fora do ar:', c)
                else:
                    cont['tinha'] += 1
            pilha.extend(o.values())
        elif isinstance(o, list):
            pilha.extend(o)
    cache_log('capas do json:', cont, 'limite', limite)
    return faltou


def laco_cache():
    time.sleep(20)
    while True:
        try:
            st, _, d = remoto('/loja/api/loja', 10)
            cache_log('ciclo: remoto', st)
            if st == 200:
                cache_salvar('api-loja.json', d)
                for cam, nome in (('/loja/loja.html', 'loja.html'), ('/loja/temperatura.js', 'temperatura.js'),
                                  ('/loja/api/loja/snes', 'api-loja-snes.json'), ('/loja/api/online', 'api-online.json')):
                    s, _, c = remoto(cam, 15)
                    if s == 200:
                        cache_salvar(nome, c)
                faltou = cache_capas_do_json(json.loads(d), limite=60)   # 60 por ciclo até o cache bater completo
                try:
                    faltou += cache_capas_do_json(json.load(open(os.path.join(CACHE_LOJA, 'api-loja-snes.json'),
                                                                 encoding='utf-8')), limite=max(0, 60 - faltou))
                except (OSError, ValueError):
                    pass
                if faltou:
                    cache_log(f'capas: +{faltou}')
                os.makedirs(CACHE_LOJA, exist_ok=True)
                meta = {'quando': int(time.time()), 'quando_txt': time.strftime('%d/%m %H:%M')}
                with open(os.path.join(CACHE_LOJA, 'meta.json') + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False)
                os.replace(os.path.join(CACHE_LOJA, 'meta.json') + '.tmp', os.path.join(CACHE_LOJA, 'meta.json'))
        except Exception as e:
            cache_log('ciclo falhou:', e)
        time.sleep(300)


_TIPO_DOM = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.json': 'application/json',
             '.jpg': 'image/jpeg', '.png': 'image/png'}


def cache_loja_ler(caminho):
    """Servindo /loja/<caminho> do cachecake (o notebook não responde). (tipo, dados) ou (None, b'')."""
    cam = caminho[len('/loja/'):] if caminho.startswith('/loja/') else caminho
    for i in cam.split('/'):
        if i in ('', '.') or '..' in i or i.startswith('.'):
            return 503, 'application/json', json.dumps({'erro': 'caminho de cache inválido'}).encode()
    try:
        for nome in ('loja.html', 'temperatura.js'):
            if cam == nome and os.path.exists(os.path.join(CACHE_LOJA, nome)):
                return _TIPO_DOM[os.path.splitext(nome)[1]], open(os.path.join(CACHE_LOJA, nome), 'rb').read()
        if cam == 'api/loja':
            d = open(os.path.join(CACHE_LOJA, 'api-loja.json'), 'rb').read()
            cat = json.loads(d)
            try:   # mesmo enxerto do online: o que a box copiou para o pendrive do PS2
                cat['ps2'] = json.load(open(os.path.join(PASTA, 'ps2', 'no-ps2.json'), encoding='utf-8'))
            except (OSError, ValueError):
                pass
            cat['cache'] = {'quando': cache_meta().get('quando_txt', '?')}
            d = json.dumps(cat, ensure_ascii=False).encode()
            return 'application/json', d
        if cam == 'api/loja/snes':
            d = open(os.path.join(CACHE_LOJA, 'api-loja-snes.json'), 'rb').read()
            try:
                s = json.loads(d)
                s['cache'] = {'quando': cache_meta().get('quando_txt', '?')}
                d = json.dumps(s, ensure_ascii=False).encode()
            except ValueError:
                pass
            return 'application/json', d
        if cam == 'api/online':
            d = open(os.path.join(CACHE_LOJA, 'api-online.json'), 'rb').read()
            try:
                s = json.loads(d)
                s['cache'] = {'quando': cache_meta().get('quando_txt', '?')}
                d = json.dumps(s, ensure_ascii=False).encode()
            except ValueError:
                pass
            return 'application/json', d
        if cam.startswith('capas/'):
            arq = os.path.join(CACHE_LOJA, cam)
            if os.path.isfile(arq):
                return _TIPO_DOM.get(os.path.splitext(cam)[1].lower(), 'application/octet-stream'), open(arq, 'rb').read()
    except OSError:
        pass
    return None, b''


# ---------- 🎵 Música de fundo da loja (24/10/2026) ----------
# As faixas do pacote (ps2/trilhas) são originais e livres. As do usuário vêm da pasta MUSICAS/ do pendrive da box
# (mp3/ogg/wav/flac/m4a que a pessoa mesma pôs lá): o ffmpeg do Termux converte para o som do PS2 (22050 Hz mono
# 16 bits), até 90 s com entrada e saída suaves, em ps2/trilhas-usuario. Nada disso vai no pacote.
MUSICAS_EXT = ('.mp3', '.ogg', '.wav', '.flac', '.m4a', '.opus')
TRILHAS_USUARIO = os.path.join(PASTA, 'ps2', 'trilhas-usuario')


def pasta_musicas():
    try:
        for d in sorted(os.listdir('/storage')):
            m = os.path.join('/storage', d, 'MUSICAS')
            if '-' in d and os.path.isdir(m):
                return m
    except OSError:
        pass
    return os.environ.get('PS2_MUSICAS')


def converter_musicas():
    """Converte as músicas novas de MUSICAS/ e tira da lista as que sumiram. Devolve quantas faixas do usuário há."""
    origem = pasta_musicas()
    os.makedirs(TRILHAS_USUARIO, exist_ok=True)
    indice = os.path.join(TRILHAS_USUARIO, 'trilhas.json')
    try:
        antigas = {t['origem']: t for t in json.load(open(indice, encoding='utf-8'))}
    except (OSError, ValueError, KeyError):
        antigas = {}
    lista = []
    # O FAT32 da TV box fica a raiz: o termux não abre o diretório nem o arquivo (PermissionError 13, 25/10/2026).
    # Tenta o acesso direto; negado, lista com o root e converte cada um com o ffmpeg do termux rodando root,
    # devolvendo o .raw ao termux (chown 10081) para o os.replace seguir no fluxo de sempre.
    via_root, ffmpeg = False, shutil.which('ffmpeg') or 'ffmpeg'
    nomes = []
    if origem:
        try:
            nomes = sorted(n for n in os.listdir(origem) if n.lower().endswith(MUSICAS_EXT))
        except OSError:
            nomes = [s for s in como_root('ls -1 ' + shlex.quote(origem), 15).splitlines()
                     if s.lower().endswith(MUSICAS_EXT)]
            via_root = bool(nomes)
    for n in (sorted(nomes) if via_root else nomes):
        arq = os.path.join(origem, n)
        q = shlex.quote
        if via_root:
            assinatura = como_root('stat -c %s:%Y ' + q(arq), 15).strip()
            if ':' not in assinatura:   # arquivo sumiu a meio da listagem
                continue
        else:
            assinatura = f'{os.path.getsize(arq)}:{int(os.path.getmtime(arq))}'
        fid = 'u-' + re.sub(r'[^a-z0-9]+', '-', n.rsplit('.', 1)[0].lower()).strip('-')[:40]
        t = antigas.get(n)
        if t and t.get('assinatura') == assinatura and os.path.exists(os.path.join(TRILHAS_USUARIO, t['id'] + '.raw')):
            lista.append(t)
            continue
        saida = os.path.join(TRILHAS_USUARIO, fid + '.raw')
        opcoes = ['-v', 'error', '-y', '-i', q(arq) if via_root else arq, '-t', '90',
                  '-af', 'afade=t=in:d=1,areverse,afade=t=in:d=2,areverse', '-ac', '1', '-ar', '22050',
                  '-f', 's16le', q(saida + '.tmp') if via_root else saida + '.tmp']
        if via_root:
            cmd = ('env LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib ' + q(ffmpeg) + ' ' + ' '.join(opcoes)
                   + ' && [ -s ' + q(saida + '.tmp') + ' ] && chown 10081 ' + q(saida + '.tmp'))
            p = subprocess.run(['su', '-c', cmd], capture_output=True, text=True, timeout=300)
            ok, err = p.returncode == 0, (p.stdout + p.stderr).strip()[-200:]
        else:
            r = subprocess.run(['ffmpeg'] + opcoes, capture_output=True, timeout=300)
            ok, err = r.returncode == 0, (r.stderr or b'')[-200:]
        if not ok or not os.path.getsize(saida + '.tmp'):
            print(f'música {n}: ffmpeg falhou: {err}', flush=True)
            como_root('rm -f ' + q(saida + '.tmp'), 15) if via_root else None
            continue
        os.replace(saida + '.tmp', saida)
        lista.append({'id': fid, 'titulo': n.rsplit('.', 1)[0][:60], 'segundos': round(os.path.getsize(saida) / 44100, 1),
                      'credito': 'sua música (pasta MUSICAS do pendrive)', 'origem': n, 'assinatura': assinatura})
    for t in antigas.values():   # as que saíram do pendrive
        if t not in lista and not any(x['id'] == t['id'] for x in lista):
            try:
                os.remove(os.path.join(TRILHAS_USUARIO, t['id'] + '.raw'))
            except OSError:
                pass
    with open(indice + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(indice + '.tmp', indice)
    return len(lista)


def laco_musicas():
    while True:
        try:
            converter_musicas()
        except Exception as e:
            print('músicas do pendrive:', e, flush=True)
        time.sleep(600)


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


def pagina_no_ps2(msg='', online=False):
    """💾 Jogos no pendrive do PS2 (ps2/no-ps2.json, anotados pelo navegador_servidor nas cópias) com ▶ Jogar direto.
    online=True (🌐 Jogar online, 23/10/2026): mesma lista, mas abre pelo OPL oficial — o OPL-RA ocupa a placa de rede
    com a telemetria das conquistas e o jogo dá "erro de hardware" na configuração de rede."""
    try:
        jogos = json.load(open(os.path.join(PASTA, 'ps2', 'no-ps2.json'), encoding='utf-8'))
    except (OSError, ValueError):
        jogos = {}
    ind, itens = indice_ra(), ''
    for arq in sorted(jogos, key=lambda a: a[12:].lower() if re.match(r'^[A-Z]{4}_\d{3}\.\d{2}\.', a) else a.lower()):
        serial = arq[:11] if re.match(r'^[A-Z]{4}_\d{3}\.\d{2}\.', arq) else ''
        nome = os.path.splitext(arq[12:] if serial else arq)[0]
        ra = ind.get(serial) or {}
        tag = f'🏆 {ra.get("total", "")} conquistas · ' if ra.get('id') and not online else ''
        itens += (f'<a class="b" href="/no-ps2/jogar?arquivo={urllib.parse.quote(arq)}{"&online=1" if online else ""}">'
                  f'{"🌐" if online else "▶"} {html.escape(nome)}'
                  f'<div class="p">{tag}{html.escape(serial or "sem código")} · {html.escape(jogos[arq].get("pasta", "DVD"))}'
                  + (f' · copiado em {html.escape(jogos[arq]["quando"])}' if jogos[arq].get('quando') else '') + '</div></a>')
    if not itens:
        itens = ('<div class="msg">Nenhum jogo nas pastas DVD e CD do pendrive do PS2. Na Loja, use 🎮 Instalar no '
                 'pendrive USB do PS2.</div>')
    # a lista é lida do pendrive do PS2 quando o navegador abre (navegador_servidor.listar_jogos_pendrive)
    itens = (f'<a class="b" href="/no-ps2/ler{"?online=1" if online else ""}">🔄 Ler o pendrive de novo</a>') + itens
    aviso = f'<div class="msg">{html.escape(msg)}</div>' if msg else ''
    if online:
        return ('<h1>🌐 Jogar online</h1><div class="msg">Abre pelo OPL normal (sem conquistas), com a rede livre para o '
                'jogo. Na configuração de rede do jogo use IP automático (DHCP).</div>' + aviso +
                '<div class="lista"><a class="b" href="/">← Voltar</a>' + itens + '</div>')
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
            + f'<a class="b" href="{html.escape(LOJA)}">🛒 Loja PS2</a>'
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


# ---------- 🌐 Evento online (23/10/2026): partidas marcadas no notebook (evento_online.py, /evento no WhatsApp) ----------
EVENTOS = os.path.join(PASTA, 'ps2', 'eventos.json')   # cópia local: vale mesmo com o notebook fora do alcance
DNS_EVENTO = os.path.join(PASTA, 'dns-evento')          # "IP INÍCIO FIM" (epoch): o henbox-root.sh (root) aplica
REDE = '/data/local/henbox-rede'                        # estado do PS2 no cabo, escrito pelo henbox-root.sh


# ---------- 📶 Wi-Fi da TV box (23/10/2026): busca pelo iw (root) e o app PS2 Navegador (Wifi.java) conecta ----------
WIFI_ESTADO = {'estado': '', 'ssid': '', 'msg': '', 't': 0}   # último aviso do Wifi.java (POST /wifi/resposta)


def como_root(cmd, timeout=30):
    try:
        return subprocess.run(['su', '-c', cmd], capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def _nome_iw(t):   # o iw escreve bytes fora do ASCII como \xNN
    b = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), t).encode('latin-1', 'replace')
    return b.decode('utf-8', 'replace').strip()


def wifi_atual():
    m = re.search(r'SSID: (.*)', como_root('iw dev wlan0 link', 10))
    return _nome_iw(m.group(1)) if m else ''


def wifi_redes():
    """[{ssid, sinal (dBm), segura}] da busca do iw, do sinal mais forte para o mais fraco (sem nomes repetidos)."""
    saida = como_root('iw dev wlan0 scan 2>/dev/null || iw dev wlan0 scan dump', 30)
    redes = {}
    for bloco in re.split(r'\n(?=BSS )', saida):
        m = re.search(r'\n\s*SSID: (.*)', bloco)
        if not m or not m.group(1).strip():
            continue   # rede oculta
        ssid = _nome_iw(m.group(1))
        s = re.search(r'signal: (-?[\d.]+)', bloco)
        sinal = float(s.group(1)) if s else -100.0
        segura = bool(re.search(r'RSN:|WPA:|Privacy', bloco))
        if ssid not in redes or sinal > redes[ssid]['sinal']:
            redes[ssid] = {'ssid': ssid, 'sinal': sinal, 'segura': segura}
    return sorted(redes.values(), key=lambda r: -r['sinal'])


def barras(dbm):
    return '▂▄▆█' if dbm >= -55 else '▂▄▆' if dbm >= -67 else '▂▄' if dbm >= -78 else '▂'


def pagina_wifi():
    atual, est = wifi_atual(), WIFI_ESTADO
    recente = time.time() - est['t'] < 300
    conectando = recente and est['estado'] == 'conectando'
    topo = (f'<div class="msg">Conectada em <b>{html.escape(atual)}</b></div>' if atual
            else '<div class="msg">Sem Wi-Fi agora</div>')
    if recente and est['msg']:
        cor = {'ok': '#3fb950', 'erro': '#f85149'}.get(est['estado'], '#ffd166')
        topo += (f'<div class="msg" style="color:{cor}">{html.escape(est["ssid"])}: {html.escape(est["msg"])}</div>')
    itens = ''
    if not conectando:
        for r in wifi_redes():
            liga = '✔ ' if r['ssid'] == atual else ''
            itens += (f'<a class="b" href="/wifi/rede?ssid={urllib.parse.quote(r["ssid"])}">{liga}{html.escape(r["ssid"])}'
                      f'<div class="p">{barras(r["sinal"])} {r["sinal"]:.0f} dBm · {"🔒 com senha" if r["segura"] else "aberta"}</div></a>')
        itens = itens or '<div class="msg">Nenhuma rede encontrada.</div>'
    return (('<meta http-equiv="refresh" content="3">' if conectando else '') + '<h1>📶 Wi-Fi da TV box</h1>' + topo
            + '<div class="lista"><a class="b" href="/">← Voltar</a>'
            + ('' if conectando else '<a class="b" href="/wifi">🔄 Buscar de novo</a>') + itens + '</div>')


def pagina_wifi_rede(ssid):
    segura = next((r['segura'] for r in wifi_redes() if r['ssid'] == ssid), True)
    campo = ('<div class="msg">Senha (rede já salva na box: pode deixar em branco):</div><input name="senha" autocomplete="off" style="margin:0 20px 12px;width:560px;'
             'font-size:24px;padding:10px;border-radius:8px;border:0">' if segura else
             '<div class="msg">Rede aberta, sem senha.</div>')
    return (f'<h1>📶 {html.escape(ssid)}</h1><form method="post" action="/wifi/conectar">'
            f'<input type="hidden" name="ssid" value="{html.escape(ssid)}">{campo}'
            '<div class="msg" style="color:#9fb4e0;font-size:15px">Se não conectar em 60 s, a box volta sozinha para a rede '
            'atual. Fora da rede de casa, a Loja e os vídeos vêm pela internet (Cloudflare); o PS2 no cabo da box continua '
            'ligado.</div><div class="lista" style="height:auto"><button class="b" style="width:100%;border:0;font-size:inherit;'
            'text-align:left">📶 Conectar</button><a class="b" href="/wifi">← Voltar</a></div></form>')


def wifi_conectar(ssid, senha):
    if not ssid or len(ssid.encode()) > 32:
        return 'nome de rede inválido'
    if senha and not 8 <= len(senha) <= 63:
        return 'a senha do Wi-Fi tem de 8 a 63 caracteres'
    WIFI_ESTADO.update(estado='conectando', ssid=ssid, msg='conectando…', t=time.time())
    como_root('am startservice -n br.ps2nav/.Wifi --es ssid ' + shlex.quote(ssid)
              + ' --es senha ' + shlex.quote(senha), 15)
    return 'ok'


def ler_eventos():
    try:
        return [e for e in json.load(open(EVENTOS, encoding='utf-8')) if (e.get('inicio') or 0) + e.get('depois', 0) > time.time()]
    except (OSError, ValueError):
        return []


def janela_dns():
    """A janela do DNS do evento em andamento (ou do próximo); vazio se não há evento com DNS."""
    agora = time.time()
    for e in sorted(ler_eventos(), key=lambda e: e.get('inicio') or 0):
        if e.get('inicio') and e.get('dns') and e['inicio'] + e.get('depois', 0) > agora:
            return f"{e['dns'][0]} {e['inicio'] - e.get('antes', 3600)} {e['inicio'] + e.get('depois', 0)}"
    try:   # kit online aplicado pela central do celular (central.py, 24/10/2026): {"ip", "ate"} em ~/ps2nav/dns-kit.json
        k = json.load(open(os.path.join(PASTA, 'dns-kit.json')))
        if k.get('ip') and k.get('ate', 0) > agora:
            return f"{k['ip']} {int(agora) - 60} {int(k['ate'])}"
    except (OSError, ValueError):
        pass
    return ''


def laco_eventos():
    n = 0
    while True:
        if n % 5 == 0:   # do notebook a cada 5 min
            st, _, d = remoto('/eventos', timeout=20)
            if st == 200:
                try:
                    evs = json.loads(d)
                    with open(EVENTOS + '.tmp', 'w', encoding='utf-8') as f:
                        json.dump(evs, f, ensure_ascii=False)
                    os.replace(EVENTOS + '.tmp', EVENTOS)
                except (OSError, ValueError) as e:
                    print('eventos:', e, flush=True)
        try:
            j = janela_dns()
            if (open(DNS_EVENTO).read().strip() if os.path.exists(DNS_EVENTO) else '') != j:
                with open(DNS_EVENTO, 'w') as f:
                    f.write(j + '\n' if j else '')
        except OSError as e:
            print('dns-evento:', e, flush=True)
        n += 1
        time.sleep(60)


def ler_rede(nome):
    try:
        return open(os.path.join(REDE, nome)).read().strip()
    except OSError:
        return ''


def estado_evento():
    cabo = ler_rede('estado').split()
    try:   # captura-jogo.py (root): partidas online gravadas para achar o placar
        cap = json.loads(ler_rede('capturas/resumo.json') or '{}')
    except ValueError:
        cap = {}
    return {'cabo': cabo[0] if cabo else '', 'dns_ativo': ler_rede('dns-evento-ativo'), 'janela': janela_dns(),
            'eventos': len(ler_eventos()), 'captura': cap}


def quando_txt(ts):
    falta = ts - time.time()
    d = time.localtime(ts)
    dia = 'hoje' if time.strftime('%d/%m', d) == time.strftime('%d/%m') else time.strftime('%d/%m', d)
    if falta > 0:
        h, m = int(falta // 3600), int(falta % 3600 // 60)
        return f'{dia} às {time.strftime("%H:%M", d)} · falta {f"{h} h " if h else ""}{m} min'
    return f'começou às {time.strftime("%H:%M", d)} · rolando agora'


def pagina_evento():
    evs = sorted(ler_eventos(), key=lambda e: e.get('inicio') or 0)
    est = estado_evento()
    itens = ''
    for e in evs:
        if est['dns_ativo'] and e.get('dns') and est['dns_ativo'] == e['dns'][0]:
            dns = f'✅ DNS {e["dns"][0]} ligado no PS2 (automático)'
        elif est['cabo']:
            dns = f'⏳ DNS {", ".join(e.get("dns") or ["?"])} entra sozinho 1 h antes'
        else:
            dns = f'⚠ PS2 fora do cabo da box: ponha o DNS {", ".join(e.get("dns") or ["?"])} na rede do jogo'
        itens += (f'<div class="ev"><div class="t">🎮 {html.escape(e.get("jogo") or "?")}</div>'
                  f'<div class="q">🕗 {html.escape(quando_txt(e["inicio"]) if e.get("inicio") else "horário a confirmar")}</div>'
                  + (f'<div class="s">🖥️ Servidor: <b>{html.escape(e["servidor"])}</b></div>' if e.get('servidor') else '')
                  + f'<div class="d">{html.escape(dns)}</div></div>')
    if not itens:
        itens = '<div class="msg">Nenhum evento online marcado. No WhatsApp: /evento + o anúncio.</div>'
    cap = est.get('captura') or {}
    if cap.get('gravando'):
        itens += f'<div class="msg">🔴 Gravando a partida para o placar ({cap.get("pacotes", 0)} pacotes)</div>'
    return ('<meta http-equiv="refresh" content="30"><style>.ev{margin:0 0 12px;padding:12px 16px;background:#132a57;'
            'border-radius:12px;border-left:5px solid #ffd166}.ev .t{font-size:24px}.ev .q{color:#ffd166;margin:4px 0}'
            '.ev .s{font-size:18px}.ev .s b{color:#7ee787}.ev .d{color:#9fb4e0;font-size:16px;margin-top:4px}</style>'
            '<h1>🌐 Evento online</h1><div class="lista">' + itens + '<a class="b" href="/">← Voltar</a></div>')


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
        if st != 200:   # notebook fora: a lista salva no cache da loja (sabe os ROMs que já estão no pendrive)
            t, c = cache_loja_ler('/loja/api/loja/snes')
            if t:
                st, d = 200, c
                cache_log('loja_snes: servido do cache da loja')
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
        bruto = self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0)
        try:
            corpo = json.loads(bruto or b'{}')
        except ValueError:
            corpo = {}
        if u.path == '/wifi/resposta':   # o Wifi.java avisa cada passo (só daqui da box)
            if self.client_address[0] != '127.0.0.1' or not isinstance(corpo, dict):
                return self.json({'ok': False}, 403)
            WIFI_ESTADO.update(estado=str(corpo.get('estado', '')), ssid=str(corpo.get('ssid', '')),
                               msg=str(corpo.get('msg', '')), t=time.time())
            return self.json({'ok': True})
        if u.path == '/wifi/conectar':   # formulário da página 📶
            f = urllib.parse.parse_qs(bruto.decode('utf-8', 'replace'), keep_blank_values=True)
            r = wifi_conectar((f.get('ssid') or [''])[0], (f.get('senha') or [''])[0])
            if r != 'ok':
                WIFI_ESTADO.update(estado='erro', ssid=(f.get('ssid') or [''])[0], msg=r, t=time.time())
            self.send_response(303)
            self.send_header('Location', '/wifi')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
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
            if not jogo:
                return self.json({'ok': False, 'msg': 'jogo não encontrado no catálogo'})
            # 23/10/2026: o jogo não precisa mais estar no pendrive da box; senão vem do HD do notebook (host:nuvem/)
            na_box = jogo.get('instalado')
            if acao in ('api/preparar-ra', 'api/copiar-ra'):
                from ra_preparar import preparar
                iso = os.path.join(os.path.realpath(os.path.join(PASTA, 'ps2', 'jogos-box')), jogo['arquivo'])
                titulo = None
                try:
                    if not na_box:
                        import udpfs_nuvem
                        iso = udpfs_nuvem.IsoRemoto('DVD/' + jogo['arquivo'])
                    _, titulo = preparar(iso, jogo['id'], os.path.join(PASTA, 'ps2', 'ra'))
                except Exception as e:
                    if not isinstance(iso, str):
                        iso.close()
                    if acao == 'api/preparar-ra':
                        return self.json({'ok': False, 'msg': f'Sem conquistas: {e}'})
                    # copiar-ra: o jogo vai assim mesmo, só sem conquistas
                if titulo:
                    try:
                        registrar_preparado(jogo['id'], titulo, iso)
                    except Exception:
                        pass
                    if not isinstance(iso, str):
                        iso.close()
                r = navegador(f"copiar2 host:ra/{jogo['id']}.wl|mass:/RA/{jogo['id']}.wl|ra-wl:{jogo['id']}") if titulo else 'ok'
                if r != 'ok':
                    if acao == 'api/preparar-ra':   # vai para o pendrive do PS2 no "Copiar para o PS2"
                        return self.json({'ok': True, 'msg': f'🏆 {titulo} — preparado (o PS2 recebe ao copiar o jogo)'})
                    return self.json({'ok': False, 'msg': r})
                if acao == 'api/preparar-ra':
                    return self.json({'ok': True, 'msg': f'🏆 {titulo} — conquistas preparadas no pendrive do PS2'})
            if acao == 'api/copiar-ra':   # USB 1.1 do PS2: ~1 MB/s; o progresso aparece na tela do navegador
                if jogo['tamanho'] >= 4 * 1024 ** 3:
                    return self.json({'ok': False, 'msg': 'maior que 4 GB: não cabe no pendrive FAT32 do PS2'})
                origem = f"host:jogos-box/{jogo['arquivo']}" if na_box else f"host:nuvem/DVD/{jogo['arquivo']}"
                r = navegador(f"copiar2 {origem}|mass:/DVD/{jogo['arquivo']}|ra:{jogo['id']}|{jogo['tamanho']}")
                return self.json({'ok': r == 'ok', 'msg': f'Copiando {jogo["nome"]} para o pendrive USB do PS2 '
                                  f'(~{jogo["tamanho"] // 1048576 // 60 + 1} min'
                                  + ('' if na_box else ', direto do HD do notebook')
                                  + ('' if titulo else '; sem conquistas') + ')…' if r == 'ok' else r})
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
        if u.path == '/loja/api/musica':   # barra ◀ ▶ da loja: ?acao=estado|proxima|anterior|ligar|desligar|atualizar
            acao = (urllib.parse.parse_qs(u.query).get('acao') or ['estado'])[0]
            if acao == 'atualizar':
                converter_musicas()
                acao = 'estado'
            if acao not in ('estado', 'proxima', 'anterior', 'ligar', 'desligar'):
                return self.json({'erro': 'ação desconhecida'})
            r = navegador('musica ' + acao)
            try:
                return self.json(json.loads(r))
            except ValueError:
                return self.json({'erro': r})
        if u.path == '/api/ps2/temperatura':   # temperatura.js da loja pede pela raiz do site
            u = u._replace(path='/loja/api/ps2/temperatura')
        if u.path.startswith('/loja/'):
            st, tipo, d = remoto(u.path + (('?' + u.query) if u.query else ''))
            if st == 502:   # notebook fora do alcance: a loja serve do cache local (25/10/2026)
                t, d = cache_loja_ler(u.path)
                if t:
                    st, tipo = 200, t
            if u.path == '/loja/api/loja' and st == 200 and tipo.startswith('application/json'):   # + o que a box copiou para o pendrive do PS2 (no-ps2.json)
                try:
                    cat = json.loads(d)
                    cat['ps2'] = json.load(open(os.path.join(PASTA, 'ps2', 'no-ps2.json'), encoding='utf-8'))
                    d = json.dumps(cat).encode()
                except (OSError, ValueError):
                    pass
            self.send_response(st)
            self.send_header('Content-Type', tipo or 'application/octet-stream')
            self.send_header('Content-Length', str(len(d)))
            self.end_headers()
            self.wfile.write(d)
            return
        q = urllib.parse.parse_qs(u.query)
        if u.path == '/':
            ev = sorted(ler_eventos(), key=lambda e: e.get('inicio') or 0)[:1]
            botao_ev = (f'<a class="b grande" href="/evento">🌐 {html.escape(ev[0].get("jogo") or "Evento online")}'
                        f'<div class="p">{html.escape(quando_txt(ev[0]["inicio"]) if ev[0].get("inicio") else "")}</div></a>'
                        if ev else '')
            self.pagina(f'<h1>PS2</h1><div class="lista">{botao_ev}<a class="b grande" href="{html.escape(LOJA)}">🛒 Loja</a>'
                        '<a class="b grande" href="/sms">🎞 Filmes e séries (SMS)</a>'
                        '<a class="b grande" href="/no-ps2">💾 No pendrive do PS2</a>'
                        '<a class="b grande" href="/no-ps2?online=1">🌐 Jogar online</a>'
                        '<a class="b grande" href="/conquistas">🏆 Conquistas</a>'
                        '<a class="b grande" href="/wifi">📶 Wi-Fi da TV box</a>'
                        '<a class="b grande" href="/reiniciar">🔄 Reiniciar sistema</a></div>')
        elif u.path == '/wifi':
            self.pagina(pagina_wifi())
        elif u.path == '/wifi/rede':
            self.pagina(pagina_wifi_rede((q.get('ssid') or [''])[0]))
        elif u.path == '/reiniciar':   # 🔄 (24/10/2026): o navegador fecha, o PS2 volta ao PS2Link do memory card e o
            # servidor_host da box, ao achar o PS2Link, abre o navegador de novo (IOP e rede do zero)
            if q.get('sim') != ['1']:   # confirmação na página: um clique sem querer não reinicia
                return self.pagina('<h1>🔄 Reiniciar sistema</h1><div class="msg">O navegador fecha, o PS2 volta ao '
                                   '<b>PS2Link</b> e a TV box abre o navegador de novo sozinha (uns 20 segundos).</div>'
                                   '<div class="lista"><a class="b grande" href="/reiniciar?sim=1">🔄 Reiniciar agora</a>'
                                   '<a class="b" href="/">← Voltar</a></div>')
            r = navegador('sair')
            self.pagina('<h1>🔄 Reiniciando…</h1><div class="msg">' + (
                'Voltando ao PS2Link. O navegador abre de novo em uns 20 segundos.' if r == 'ok'
                else 'O navegador não está aberto no PS2 (' + html.escape(r) + ').') + '</div>')
        elif u.path == '/sms':   # SMS do cinema (23/10/2026): o navegador fecha e o SMS abre na pasta UDPFS
            r = navegador('sms')
            self.pagina('<h1>🎞 Filmes e séries</h1><div class="msg">' + (
                'Abrindo o SMS no PS2… (na 1ª vez ele é instalado no pendrive antes)</div>'
                '<div class="msg">No SMS: <b>UDPFS → CINEMA-NUVEM</b> e escolha o vídeo.'
                if r == 'ok' else html.escape(r)) + '</div><div class="lista"><a class="b" href="/">← Voltar</a></div>')
        elif u.path == '/evento':
            self.pagina(pagina_evento())
        elif u.path == '/evento/estado.json':   # o notebook confere antes do evento (evento_online.py)
            return self.json(estado_evento())
        elif u.path == '/no-ps2':
            self.pagina(pagina_no_ps2(online=bool(q.get('online'))))
        elif u.path == '/no-ps2/ler':
            r = navegador('listar-pendrive')
            if r == 'ok':
                time.sleep(4)   # as duas listas (DVD e CD) costumam voltar em 1-3 s
            self.pagina(pagina_no_ps2('Lista lida do pendrive do PS2.' if r == 'ok' else r, bool(q.get('online'))))
        elif u.path == '/no-ps2/jogar':
            arq = os.path.basename((q.get('arquivo') or [''])[0])
            try:
                registrados = json.load(open(os.path.join(PASTA, 'ps2', 'no-ps2.json'), encoding='utf-8'))
            except (OSError, ValueError):
                registrados = {}
            online = bool(q.get('online'))
            if arq not in registrados:
                return self.pagina(pagina_no_ps2('Esse jogo não está na lista do pendrive do PS2.', online))
            serial = arq[:11] if re.match(r'^[A-Z]{4}_\d{3}\.\d{2}\.', arq) else 'SLUS_000.00'
            midia = 'CD' if registrados[arq].get('pasta') == 'CD' else 'DVD'
            if online:   # OPL oficial (ps2/opl/OPNPS2LD.ELF): mesma abertura direta "bdm", rede livre para o jogo
                r = navegador(f'abrir host:opl/OPNPS2LD.ELF|{arq}|{serial}|{midia}|bdm')
                return self.pagina(pagina_no_ps2('Abrindo pelo OPL normal…' if r == 'ok' else r, True))
            # OPL-RA pelo pendrive do PS2 ("bdm"): com a lista RA/<serial>.wl tem conquistas, sem ela abre normal
            r = navegador(f'abrir host:oplra/OPL-RA-SMB.ELF|{arq}|{serial}|{midia}|bdm')
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
            return self.json({'app': 'ps2-henbox', 'conquistas': True, 'estado': True, 'central': 8785})
        elif u.path in ('/estado', '/estado.json'):   # lista de conferência da instalação (configurar.checklist)
            import configurar
            itens = configurar.checklist()
            if u.path.endswith('.json'):
                return self.json(itens)
            sinal = {True: '✅', False: '❌', None: '➖'}
            # compacto: uma linha por item, cabe na tela do PS2 (640x448) quase sem rolar
            linhas = ''.join(f'<div class="it {"ok" if i["ok"] else "nao" if i["ok"] is False else ""}">'
                             f'<b>{sinal[i["ok"]]} {html.escape(i["item"])}</b> <span>{html.escape(i["detalhe"])}</span>'
                             + (f'<div class="r">👉 {html.escape(i["resolver"])}</div>' if i['resolver'] else '') + '</div>'
                             for i in itens)
            faltam = sum(1 for i in itens if i['ok'] is False)
            self.pagina('<meta http-equiv="refresh" content="20"><style>.it{margin:0 0 5px;padding:5px 12px;'
                        'background:#13264f;border-radius:9px;font-size:15px;line-height:1.3;border-left:4px solid #5b6b8c}'
                        '.it.ok{border-color:#3fb950}.it.nao{border-color:#f85149}.it span{color:#9fb4e0}'
                        '.it .r{color:#ffd166;font-size:14px}.lista{height:372px}h1{margin:10px 20px 8px;font-size:24px}'
                        '</style><h1>🩺 Estado do PS2 Henbox · '
                        + ('tudo certo ✅' if not faltam else f'{faltam} a resolver ❌') + '</h1><div class="lista">'
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
    threading.Thread(target=laco_eventos, daemon=True).start()
    threading.Thread(target=laco_musicas, daemon=True).start()   # 🎵 MUSICAS/ do pendrive → faixas da loja
    threading.Thread(target=laco_cache, daemon=True).start()   # 🗄 cache da loja (o notebook pode estar desligado)
    ThreadingHTTPServer(('0.0.0.0', PORTA), H).serve_forever()
