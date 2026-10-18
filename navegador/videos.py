#!/usr/bin/env python3
"""Vídeos do PS2 na TV box (pedido do usuário 17/10/2026): lista de vídeos já no formato do player do navegador
(<id>.m2v MPEG-2 640x400 + <id>.pcm PCM 16 bits estéreo 22050 Hz + <id>.fim + <id>.json {"titulo"}), sem conversão.
Página inicial do navegador na box (porta 8780): botões Loja e Vídeos; tocar = manda "video <id>" ao
navegador_servidor (porta 8772), que pede ao PS2 host:video/<id>.m2v/.pcm (servidos pelo servidor_host.py).
Vídeos em ps2/video/ (na box) e, se houver remoto.json, os do notebook (videos_https.py: rede local em casa,
https://ps2videos.rodrigoflix.com fora), tocados como host:video/remoto/<id> pelo servidor_host.py.
Loja (/loja/...): a página, o catálogo e as capas vêm do notebook (videos_https.py /loja, rede local ou HTTPS, com
a chave); as ações de SNES rodam AQUI (baixa a ROM do notebook se faltar e manda o navegador gravar no pendrive do
PS2 / jogar); as de jogos de PS2 (ISO na TV box de casa) só funcionam com o notebook na mesma rede.
Uso: videos.py [porta]
"""
import html, json, os, socket, sys, time, urllib.error, urllib.parse, urllib.request
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


_cache_remoto = [0, []]


def lista_remota():
    """Vídeos do notebook (guarda 30 s; vazio se o notebook estiver fora do alcance)."""
    if time.time() - _cache_remoto[0] < 30:
        return _cache_remoto[1]
    vs = []
    try:
        cfg = json.load(open(os.path.join(PASTA, 'remoto.json')))
        for url in sorted(cfg['urls'], key=lambda u: u != _url_boa[0]):
            try:
                req = urllib.request.Request(url.rstrip('/') + '/lista', headers={'X-Chave': cfg['chave'], 'User-Agent': UA})
                vs = json.load(urllib.request.urlopen(req, timeout=3 if url.startswith('http:') else 10))
                _url_boa[0] = url
                break
            except Exception:
                continue
    except (OSError, ValueError):
        pass
    _cache_remoto[:] = [time.time(), vs]
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
                        '<a class="b grande" href="/videos">🎬 Vídeos</a></div>')
        elif u.path == '/videos':
            itens = ''.join(f'<a class="b" href="/tocar?id={urllib.parse.quote(v["id"])}">{html.escape(v["titulo"])}'
                            f'<div class="p">{v["mb"]} MB · na TV box</div></a>' for v in lista())
            itens += ''.join(f'<a class="b" href="/tocar?id=remoto/{urllib.parse.quote(v["id"])}">'
                             f'{html.escape(v["titulo"])}<div class="p">{v["mb"]} MB · do servidor em nuvem</div></a>'
                             for v in lista_remota())
            self.pagina('<h1>🎬 Vídeos</h1><div class="lista"><a class="b" href="/">← Voltar</a>'
                        + (itens or '<div class="msg">Nenhum vídeo em ps2/video na TV box.</div>') + '</div>')
        elif u.path == '/tocar':
            vid = (q.get('id') or [''])[0]
            validos = {v['id'] for v in lista()} | {'remoto/' + v['id'] for v in lista_remota()}
            if vid not in validos:
                return self.pagina('<div class="msg">Vídeo não encontrado.</div><a class="b" href="/videos">← Voltar</a>')
            r = navegador(f'video {vid}')
            self.pagina(f'<h1>🎬 Abrindo…</h1><div class="msg">{html.escape(r)}</div>'
                        '<div class="lista"><a class="b" href="/videos">← Voltar à lista</a></div>')
        else:
            self.send_error(404)


if __name__ == '__main__':
    print(f'vídeos do PS2 em http://0.0.0.0:{PORTA}/ ({VIDEOS})', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORTA), H).serve_forever()
