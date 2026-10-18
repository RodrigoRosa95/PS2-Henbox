#!/usr/bin/env python3
"""Vídeos do PS2 por HTTP(S) para a TV box (pedido do usuário 17/10/2026: assistir fora de casa).

Serve, só para leitura e só com a chave, a pasta PS2/VIDEOS-PS2 do compartilhamento PS2 do notebook (os vídeos já no
formato do player do navegador: <id>.m2v + <id>.pcm + <id>.fim + <id>.json). Em casa a TV box usa direto
http://192.168.4.135:8781; fora de casa, https://ps2videos.rodrigoflix.com (túnel Cloudflare → esta porta).
  GET  /lista                 → [{"id", "titulo", "mb"}]
  GET  /arquivo/<nome>        → o arquivo (aceita Range); HEAD também
  GET  /loja/<caminho>        → a loja do ps2-web (só leitura: página, catálogo, capas), para a TV box mostrar
  GET  /rom/<arquivo>         → ROM de SNES (a TV box baixa antes de gravar no pendrive do PS2)
  GET  /iso/DVD|CD/<arquivo>  → ISO de jogo de PS2 (Range; HEAD), lido aos pedaços pelo udpfs_nuvem.py da TV box
                                 enquanto o PS2 joga ("jogo em nuvem")
As ações da loja (gravar no pendrive, jogar) NÃO passam por aqui: quem executa é a TV box que está com o PS2.
Chave no cabeçalho "X-Chave" (arquivo videos_https.chave, criado na primeira vez).
Loja num navegador comum (18/10/2026, só olhar): abrir uma vez /loja/?chave=<chave> grava um cookie que libera só os
caminhos de leitura da loja (/loja/*) — não vale para vídeos, ROMs nem ISOs — e volta para /loja/loja.html sem a chave.
"""
import hashlib, hmac, json, os, re, secrets, sys, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASTA = os.environ.get('PS2_VIDEOS', '/media/rodrigo/01TERA/PS2/VIDEOS-PS2')
ARQ_CHAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'videos_https.chave')
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8781
NOME_OK = re.compile(r'^[A-Za-z0-9._-]+\.(m2v|pcm|fim|json)$')
JOGOS = os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2')
SNES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ps2', 'snes')
PS2_WEB = 'http://127.0.0.1:8770'
LOJA_OK = re.compile(r'^(loja\.html|temperatura\.js|api/loja|api/loja/snes|api/ps2/temperatura|capas/[^?#]+\.(jpg|png))$')

if not os.path.exists(ARQ_CHAVE):
    with open(os.open(ARQ_CHAVE, os.O_WRONLY | os.O_CREAT, 0o600), 'w') as f:
        f.write(secrets.token_urlsafe(32))
CHAVE = open(ARQ_CHAVE).read().strip()
# cookie do navegador: derivado da chave, só para a loja (quem pegar o cookie não baixa vídeo, ROM nem ISO)
COOKIE_LOJA = hmac.new(CHAVE.encode(), b'loja-navegador', hashlib.sha256).hexdigest()


def lista():
    vs = []
    for nome in sorted(os.listdir(PASTA)):
        vid = nome[:-4]
        if nome.endswith('.m2v') and os.path.exists(os.path.join(PASTA, vid + '.pcm')):
            try:
                titulo = json.load(open(os.path.join(PASTA, vid + '.json')))['titulo']
            except Exception:
                titulo = vid
            mb = (os.path.getsize(os.path.join(PASTA, nome)) + os.path.getsize(os.path.join(PASTA, vid + '.pcm'))) >> 20
            vs.append({'id': vid, 'titulo': titulo, 'mb': mb})
    return vs


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'   # conexão reaproveitada: a box pede pedaços seguidos

    def log_message(self, *a):
        pass

    def responder(self, codigo, dados=b'', tipo='application/json', extra=None):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(dados)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(dados)

    def cookie_loja(self):
        for parte in self.headers.get('Cookie', '').split(';'):
            nome, _, valor = parte.strip().partition('=')
            if nome == 'loja' and secrets.compare_digest(valor, COOKIE_LOJA):
                return True
        return False

    def entrar_loja(self):
        """/loja/ ou /loja/?chave=…: confere a chave, grava o cookie e manda para a loja (a chave sai da barra)."""
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        if secrets.compare_digest(q.get('chave', [''])[0], CHAVE):
            return self.responder(303, extra={'Location': '/loja/loja.html', 'Cache-Control': 'no-store',
                                              'Set-Cookie': f'loja={COOKIE_LOJA}; Path=/loja/; Max-Age=31536000; '
                                                            'Secure; HttpOnly; SameSite=Strict'})
        if self.cookie_loja():
            return self.responder(303, extra={'Location': '/loja/loja.html'})
        return self.responder(403, 'Abra uma vez /loja/?chave=… com a chave da TV box.'.encode(), 'text/plain; charset=utf-8')

    def tratar(self):
        if self.path == '/loja/' or self.path.startswith('/loja/?'):
            return self.entrar_loja()
        if self.path.startswith('/loja/') and self.command in ('GET', 'HEAD') and self.cookie_loja():
            return self.loja(self.path[len('/loja/'):].split('?')[0])
        if not secrets.compare_digest(self.headers.get('X-Chave', ''), CHAVE):
            return self.responder(403, b'{"erro": "chave"}')
        if self.path == '/lista':
            return self.responder(200, json.dumps(lista(), ensure_ascii=False).encode())
        if self.path.startswith('/loja/'):
            return self.loja(self.path[len('/loja/'):].split('?')[0])
        m = re.match(r'^/iso/(DVD|CD)/([^/]+)$', self.path)
        if m:
            nome = os.path.basename(urllib.parse.unquote(m.group(2)))
            caminho = os.path.join(JOGOS, m.group(1), nome)
            if not nome.lower().endswith('.iso') or not os.path.isfile(caminho):
                return self.responder(404, b'{"erro": "iso nao encontrado"}')
            return self.arquivo(caminho)
        m = re.match(r'^/rom/([^/]+)$', self.path)
        if m:
            nome = os.path.basename(urllib.parse.unquote(m.group(1)))
            if not nome.lower().endswith(('.smc', '.sfc')) or not os.path.isfile(os.path.join(SNES, nome)):
                return self.responder(404, b'{"erro": "rom nao encontrada"}')
            return self.arquivo(os.path.join(SNES, nome))
        m = re.match(r'^/arquivo/([^/]+)$', self.path)
        if not m or not NOME_OK.match(m.group(1)) or not os.path.isfile(os.path.join(PASTA, m.group(1))):
            return self.responder(404, b'{"erro": "nao encontrado"}')
        return self.arquivo(os.path.join(PASTA, m.group(1)))

    def loja(self, caminho):
        """Repassa ao ps2-web só os caminhos de leitura da loja (lista fixa)."""
        caminho = urllib.parse.unquote(caminho)
        if '..' in caminho or not LOJA_OK.match(caminho):
            return self.responder(404, b'{"erro": "nao encontrado"}')
        try:
            with urllib.request.urlopen(PS2_WEB + '/' + urllib.parse.quote(caminho), timeout=20) as r:
                dados, tipo = r.read(), r.headers.get('Content-Type', 'application/octet-stream')
        except urllib.error.HTTPError as e:
            return self.responder(e.code, b'{"erro": "ps2-web"}')
        except OSError:
            return self.responder(502, b'{"erro": "ps2-web fora do ar"}')
        self.responder(200, dados, tipo, {'Cache-Control': 'max-age=86400' if caminho.startswith('capas/') else 'no-store'})

    def arquivo(self, caminho):
        tam = os.path.getsize(caminho)
        ini, fim = 0, tam - 1
        r = re.match(r'^bytes=(\d+)-(\d*)$', self.headers.get('Range', ''))
        if r:
            ini = int(r.group(1))
            fim = min(int(r.group(2)) if r.group(2) else tam - 1, tam - 1)
            if ini >= tam:
                return self.responder(416, extra={'Content-Range': f'bytes */{tam}'})
        n = fim - ini + 1 if tam else 0
        self.send_response(206 if r else 200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(n))
        self.send_header('Accept-Ranges', 'bytes')
        if r:
            self.send_header('Content-Range', f'bytes {ini}-{fim}/{tam}')
        self.end_headers()
        if self.command == 'HEAD' or not n:
            return
        with open(caminho, 'rb') as f:
            f.seek(ini)
            while n > 0:
                d = f.read(min(n, 256 * 1024))
                if not d:
                    break
                self.wfile.write(d)
                n -= len(d)

    do_GET = do_HEAD = tratar


if __name__ == '__main__':
    print(f'vídeos do PS2 em :{PORTA} ({PASTA})', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORTA), H).serve_forever()
