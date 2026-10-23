#!/usr/bin/env python3
"""Servidor do notebook para a TV box do PS2 por HTTP(S) (pedido do usuário 17/10/2026: usar fora de casa).

Serve, só para leitura e só com a chave, a loja, as ROMs, os ISOs e o memory card. Em casa a TV box usa direto
http://192.168.4.135:8781; fora de casa, https://ps2videos.rodrigoflix.com (túnel Cloudflare → esta porta).
Os VÍDEOS por aqui (/lista e /arquivo, para o player do navegador) foram retirados em 22/10/2026: pelo HTTPS o vídeo
travava demais no PS2.
  GET  /loja/<caminho>        → a loja do ps2-web (só leitura: página, catálogo, capas), para a TV box mostrar
  GET  /rom/<arquivo>         → ROM de SNES (a TV box baixa antes de gravar no pendrive do PS2)
  GET  /iso/DVD|CD/<arquivo>  → ISO de jogo de PS2 (Range; HEAD), lido aos pedaços pelo udpfs_nuvem.py da TV box
                                 enquanto o PS2 joga ("jogo em nuvem")
As ações da loja (gravar no pendrive, jogar) NÃO passam por aqui: quem executa é a TV box que está com o PS2.
Chave no cabeçalho "X-Chave" (arquivo videos_https.chave, criado na primeira vez).
Loja num navegador comum (18/10/2026, só olhar): abrir uma vez /loja/?chave=<chave> grava um cookie que libera só os
caminhos de leitura da loja (/loja/*) — não vale para vídeos, ROMs nem ISOs — e volta para /loja/loja.html sem a chave.
Link público de divulgação (README do GitHub): /loja/?convite=<convite> faz o mesmo com o código de videos_https.convite,
separado da chave. Para cancelar o link: apagar o arquivo (ou trocar o código) e reiniciar (pm2 restart ps2-videos).
Chaves de acesso extras (22/10/2026, gerador no painel ps2-web, chaves.html): videos_https.chaves.json, relido sozinho
quando muda (revogar vale na hora, sem reiniciar). Cada uma vale como a principal (loja, vídeos, ROMs, ISOs) até ser
revogada ou vencer; o uso (última vez, MB servidos) vai para videos_https.uso.json a cada 30 s.
Teste de velocidade (22/10/2026): GET /teste = página que mede, no navegador do celular (4G), o que a TV box teria
lendo um ISO daqui; o resultado volta por POST /teste/resultado e fica em teste_velocidade.log.
Memory card na nuvem (22/10/2026): GET/PUT /mc/<nome>.bin = o cartão da chave usada (PS2/MC-NUVEM/<id da chave>/),
corpo gzip; X-Versao = SHA-256 do conteúdo (16 hex). Cada PUT guarda a versão anterior em antigos/ (as 10 últimas).
Atualização (22/10/2026): GET /atualizacao/versao.json e /atualizacao/navegador.elf = o que estiver em publicado/
(só o que for copiado para lá de propósito; a TV box baixa e regrava o pendrive do PS2).
"""
import gzip, hashlib, hmac, json, os, re, secrets, shutil, sys, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARQ_CHAVE = os.environ.get('PS2_CHAVE_ARQ') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'videos_https.chave')   # Docker: /dados
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8781
JOGOS = os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2')
SNES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ps2', 'snes')
PS2_WEB = 'http://127.0.0.1:8770'
LOJA_OK = re.compile(r'^(loja\.html|temperatura\.js|api/loja|api/loja/snes|api/ps2/temperatura|capas/[^?#]+\.(jpg|png))$')

if not os.path.exists(ARQ_CHAVE):
    with open(os.open(ARQ_CHAVE, os.O_WRONLY | os.O_CREAT, 0o600), 'w') as f:
        f.write(secrets.token_urlsafe(32))
CHAVE = open(ARQ_CHAVE).read().strip()
ARQ_CONVITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'videos_https.convite')
CONVITE = open(ARQ_CONVITE).read().strip() if os.path.exists(ARQ_CONVITE) else ''
COOKIE_PUBLICO = hmac.new(CHAVE.encode(), b'loja-publica:' + CONVITE.encode(), hashlib.sha256).hexdigest()
# cookie do navegador: derivado da chave, só para a loja (quem pegar o cookie não baixa vídeo, ROM nem ISO)
COOKIE_LOJA = hmac.new(CHAVE.encode(), b'loja-navegador', hashlib.sha256).hexdigest()
AQUI = os.path.dirname(os.path.abspath(__file__))
ARQ_CHAVES = os.path.join(AQUI, 'videos_https.chaves.json')
ARQ_USO = os.path.join(AQUI, 'videos_https.uso.json')
ARQ_TESTE = os.path.join(AQUI, 'teste_velocidade.log')
MC_NUVEM = os.environ.get('PS2_MC_NUVEM', os.path.join(JOGOS, 'MC-NUVEM'))
MC_NOME_OK = re.compile(r'^[A-Za-z0-9_-]{1,32}\.bin$')
MC_MAX = 64 << 20
PUBLICADO = os.path.join(AQUI, 'publicado')
PUB_OK = ('navegador.elf',)
_sha_pub = {}
_chaves = {'mtime': None, 'lista': []}
_uso, _trava_uso = {}, threading.Lock()


def chaves_extras():
    """Chaves do gerador do painel; relê o arquivo só quando ele muda."""
    try:
        m = os.path.getmtime(ARQ_CHAVES)
    except OSError:
        return []
    if m != _chaves['mtime']:
        try:
            _chaves['lista'] = json.load(open(ARQ_CHAVES)).get('chaves', [])
        except (OSError, ValueError):
            return _chaves['lista']
        _chaves['mtime'] = m
    return _chaves['lista']


def chave_id(chave):
    """'principal', o id de uma chave extra ativa e no prazo, ou None."""
    if not chave:
        return None
    if secrets.compare_digest(chave, CHAVE):
        return 'principal'
    agora = time.time()
    for c in chaves_extras():
        if (c.get('ativa', True) and (not c.get('expira') or c['expira'] > agora)
                and secrets.compare_digest(chave, c.get('chave', ''))):
            return c['id']
    return None


def cookie_extra(cid):
    return cid + '.' + hmac.new(CHAVE.encode(), b'loja-navegador:' + cid.encode(), hashlib.sha256).hexdigest()


def anotar_uso(cid, n=0):
    with _trava_uso:
        u = _uso.setdefault(cid, {'ultimo': 0, 'bytes': 0})
        u['ultimo'] = int(time.time())
        u['bytes'] += n


def gravar_uso():
    """A cada 30 s soma o uso novo ao videos_https.uso.json (o painel mostra)."""
    while True:
        time.sleep(30)
        with _trava_uso:
            novo = dict(_uso)
            _uso.clear()
        if not novo:
            continue
        try:
            total = json.load(open(ARQ_USO))
        except (OSError, ValueError):
            total = {}
        for cid, u in novo.items():
            t = total.setdefault(cid, {'ultimo': 0, 'bytes': 0})
            t['ultimo'] = max(t['ultimo'], u['ultimo'])
            t['bytes'] += u['bytes']
        tmp = ARQ_USO + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(total, f)
        os.replace(tmp, ARQ_USO)


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
            if nome == 'loja' and (secrets.compare_digest(valor, COOKIE_LOJA)
                                   or (CONVITE and secrets.compare_digest(valor, COOKIE_PUBLICO))):
                return True
            if nome == 'loja' and '.' in valor:   # cookie de uma chave extra: some quando ela é revogada
                cid = valor.split('.', 1)[0]
                if secrets.compare_digest(valor, cookie_extra(cid)) and any(
                        c['id'] == cid and chave_id(c.get('chave')) == cid for c in chaves_extras()):
                    return True
        return False

    def entrar_loja(self):
        """/loja/ ou /loja/?chave=…: confere a chave, grava o cookie e manda para a loja (a chave sai da barra)."""
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        if secrets.compare_digest(q.get('chave', [''])[0], CHAVE):
            return self.responder(303, extra={'Location': '/loja/loja.html', 'Cache-Control': 'no-store',
                                              'Set-Cookie': f'loja={COOKIE_LOJA}; Path=/loja/; Max-Age=31536000; '
                                                            'Secure; HttpOnly; SameSite=Strict'})
        cid = chave_id(q.get('chave', [''])[0])
        if cid and cid != 'principal':
            return self.responder(303, extra={'Location': '/loja/loja.html', 'Cache-Control': 'no-store',
                                              'Set-Cookie': f'loja={cookie_extra(cid)}; Path=/loja/; Max-Age=31536000; '
                                                            'Secure; HttpOnly; SameSite=Strict'})
        if CONVITE and secrets.compare_digest(q.get('convite', [''])[0], CONVITE):
            return self.responder(303, extra={'Location': '/loja/loja.html', 'Cache-Control': 'no-store',
                                              'Set-Cookie': f'loja={COOKIE_PUBLICO}; Path=/loja/; Max-Age=2592000; '
                                                            'Secure; HttpOnly; SameSite=Lax'})
        if self.cookie_loja():
            return self.responder(303, extra={'Location': '/loja/loja.html'})
        return self.responder(403, 'Abra uma vez /loja/?chave=… com a chave da TV box.'.encode(), 'text/plain; charset=utf-8')

    def tratar(self):
        if self.path == '/loja/' or self.path.startswith('/loja/?'):
            return self.entrar_loja()
        if self.path.startswith('/loja/') and self.command in ('GET', 'HEAD') and self.cookie_loja():
            return self.loja(self.path[len('/loja/'):].split('?')[0])
        if self.path == '/teste' and self.command in ('GET', 'HEAD'):
            return self.responder(200, open(os.path.join(AQUI, 'teste_velocidade.html'), 'rb').read(),
                                  'text/html; charset=utf-8', {'Cache-Control': 'no-store'})
        self.cid = chave_id(self.headers.get('X-Chave', ''))
        if not self.cid:
            return self.responder(403, b'{"erro": "chave"}')
        anotar_uso(self.cid)
        if self.path == '/teste/iso':   # ISO para o teste: o Hyper SF2 (o do teste real) ou o maior da pasta DVD
            pasta = os.path.join(JOGOS, 'DVD')
            isos = [n for n in os.listdir(pasta) if n.lower().endswith('.iso')]
            nome = next((n for n in isos if 'Hyper Street Fighter' in n),
                        max(isos, key=lambda n: os.path.getsize(os.path.join(pasta, n))))
            return self.responder(200, json.dumps({'nome': 'DVD/' + nome,
                                                   'tam': os.path.getsize(os.path.join(pasta, nome))}).encode())
        m = re.match(r'^/mc/([^/?]+)$', self.path)
        if m:
            return self.memory_card(m.group(1))
        m = re.match(r'^/atualizacao/([^/?]+)$', self.path)
        if m and self.command in ('GET', 'HEAD'):
            return self.atualizacao(m.group(1))
        if self.path == '/teste/resultado' and self.command == 'POST':
            try:
                r = json.loads(self.rfile.read(min(int(self.headers.get('Content-Length', 0)), 8192)) or b'{}')
            except ValueError:
                return self.responder(400, b'{"erro": "json"}')
            r.update(chave=self.cid, ip=self.headers.get('CF-Connecting-IP', self.client_address[0]),
                     quando=time.strftime('%d/%m/%Y %H:%M:%S'))
            with open(ARQ_TESTE, 'a') as f:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
            return self.responder(200, b'{"ok": true}')
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
        return self.responder(404, b'{"erro": "nao encontrado"}')

    def memory_card(self, nome):
        """Cartão da chave usada: GET devolve (gzip) com X-Versao; PUT grava e guarda a versão anterior."""
        if not MC_NOME_OK.match(nome):
            return self.responder(404, b'{"erro": "nome"}')
        pasta = os.path.join(MC_NUVEM, self.cid)
        arq = os.path.join(pasta, nome)
        if self.command in ('GET', 'HEAD'):
            if not os.path.isfile(arq):
                return self.responder(404, b'{"erro": "sem cartao"}')
            dados = open(arq, 'rb').read()
            versao = hashlib.sha256(dados).hexdigest()[:16]
            if self.headers.get('X-Versao-Local') == versao:
                return self.responder(304, extra={'X-Versao': versao})
            return self.responder(200, gzip.compress(dados, 6), 'application/octet-stream',
                                  {'Content-Encoding': 'gzip', 'X-Versao': versao, 'Cache-Control': 'no-store'})
        if self.command != 'PUT':
            return self.responder(405, b'{"erro": "metodo"}')
        n = int(self.headers.get('Content-Length', 0))
        if not 0 < n <= MC_MAX:
            return self.responder(413, b'{"erro": "tamanho"}')
        corpo = self.rfile.read(n)
        try:
            dados = gzip.decompress(corpo) if self.headers.get('Content-Encoding') == 'gzip' else corpo
        except (OSError, EOFError):
            return self.responder(400, b'{"erro": "gzip"}')
        if not 0 < len(dados) <= MC_MAX:
            return self.responder(413, b'{"erro": "tamanho"}')
        versao = hashlib.sha256(dados).hexdigest()[:16]
        os.makedirs(os.path.join(pasta, 'antigos'), exist_ok=True)
        if os.path.isfile(arq):
            atual = hashlib.sha256(open(arq, 'rb').read()).hexdigest()[:16]
            if atual == versao:
                return self.responder(200, b'{"ok": true}', extra={'X-Versao': versao})
            # guarda a anterior (marca quando outra box gravou no meio: a base não era a versão atual)
            base = self.headers.get('X-Base', '')
            sufixo = '' if not base or base == atual else '-conflito'
            shutil.copy2(arq, os.path.join(pasta, 'antigos', f'{nome}.{time.strftime("%Y%m%d-%H%M%S")}{sufixo}'))
            antigos = sorted(os.listdir(os.path.join(pasta, 'antigos')))
            for velho in antigos[:-10]:
                os.remove(os.path.join(pasta, 'antigos', velho))
        tmp = arq + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(dados)
        os.replace(tmp, arq)
        return self.responder(200, b'{"ok": true}', extra={'X-Versao': versao})

    def atualizacao(self, nome):
        """Arquivos publicados de propósito em publicado/ (hoje só o navegador.elf) e o versao.json deles."""
        if nome == 'versao.json':
            saida = {}
            for n in PUB_OK:
                arq = os.path.join(PUBLICADO, n)
                if os.path.isfile(arq):
                    st = os.stat(arq)
                    chave = (st.st_mtime_ns, st.st_size)
                    if _sha_pub.get(n, (None,))[0] != chave:
                        _sha_pub[n] = (chave, hashlib.sha256(open(arq, 'rb').read()).hexdigest())
                    saida[n] = {'sha256': _sha_pub[n][1], 'tam': st.st_size}
            return self.responder(200, json.dumps(saida).encode(), extra={'Cache-Control': 'no-store'})
        if nome not in PUB_OK or not os.path.isfile(os.path.join(PUBLICADO, nome)):
            return self.responder(404, b'{"erro": "nao publicado"}')
        return self.arquivo(os.path.join(PUBLICADO, nome))

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
                anotar_uso(getattr(self, 'cid', None) or '?', len(d))

    do_GET = do_HEAD = do_POST = do_PUT = tratar


if __name__ == '__main__':
    print(f'servidor do PS2 (loja, ROMs, ISOs, memory card) em :{PORTA}', flush=True)
    threading.Thread(target=gravar_uso, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', PORTA), H).serve_forever()
