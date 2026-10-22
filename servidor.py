#!/usr/bin/env python3
"""Página do monitor PS2 + TV box (http://127.0.0.1:8770) — pedido do usuário 16/10/2026.

Arquivos estáticos desta pasta (index.html, status.json gravado pelo monitor-ps2-tvbox.sh, capas/) e uma API:
  GET  /api/jogos    jogos da pasta DVD do pendrive da TV box, com capa (baixa as que faltam em segundo plano)
  GET  /api/proximo  jogo marcado para o próximo início do OPL (mc0:/OPL/conf_last.cfg pelo FTP do wLaunchELF)
  POST /api/proximo  {"id": "SCUS_974.81"} grava o próximo jogo (ps2-proximo-jogo.sh)
  POST /api/jogar    {"id": ...} abre o jogo na hora (caminho 2: PS2Link + Neutrino, ps2-jogar.sh)
  POST /api/sistema  {"acao": "reiniciar"|"desligar"} reset/poweroff do PS2 pelo PS2Link (ps2client)
  GET  /api/estatisticas  tempo jogado por jogo, hoje/semana/total e últimas sessões (estatisticas.json)
  GET/POST /api/ps2/temperatura  temperatura do PS2 lida pelos apps nossos (temperatura.py)
  GET  /api/chaves   chaves de acesso ao jogo em nuvem (chaves.py, página chaves.html; só da rede local)
  POST /api/chaves/criar {"nome", "dias"} | /api/chaves/revogar|reativar|apagar {"id"}
Publica o PS2 no painel do HA (painel_ha.py). Também ouve os comandos de voz da Echo pelo HA ("Alexa, abrir GTA", "Alexa, desligar o PS2"): ver voz.py.
"""
import json, os, socket, subprocess, threading, time, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PASTA = os.path.dirname(os.path.abspath(__file__))
CAPAS = os.path.join(PASTA, 'capas')
SCRIPT = os.path.expanduser('~/.local/bin/ps2-proximo-jogo.sh')
TVBOX, PS2_FTP = os.environ.get('PS2_TVBOX', '192.168.4.121'), os.environ.get('PS2_FTP', '192.168.4.230')
PS2LINK = PS2_FTP  # PS2Link e wLaunchELF usam o mesmo IP fixo
_cache = {'t': 0, 'jogos': []}
_trava = threading.Lock()
_trava_ps2 = threading.Lock()   # um comando por vez para o PS2 (página e voz)


def porta_aberta(ip, porta, t=2):
    try:
        socket.create_connection((ip, porta), timeout=t).close()
        return True
    except OSError:
        return False


def ping(ip):
    return subprocess.run(['ping', '-c1', '-W1', ip], capture_output=True).returncode == 0


def jogar(jid):
    """Caminho 2. Devolve (ok, mensagem)."""
    with _trava_ps2:
        r = subprocess.run([os.path.expanduser('~/.local/bin/ps2-jogar.sh'), jid + '.'],
                           capture_output=True, text=True, timeout=90)
    linhas = (r.stdout or r.stderr).strip().splitlines()
    return r.returncode == 0, (linhas[-1] if linhas else ''), r.returncode


def sistema(acao):
    """Reiniciar (volta ao PS2Link) ou desligar o PS2. Só funciona com o PS2 no PS2Link: os comandos do
    ps2client são UDP sem resposta e o PS2Link não abre porta TCP, então confere ping, FTP fechado e nenhum jogo aberto."""
    if acao == 'loja-nativa':   # loja nativa no PS2 (AthenaEnv, loja-ps2/main.js)
        with _trava_ps2:
            r = subprocess.run([os.path.expanduser('~/.local/bin/ps2-loja-nativa.sh')], capture_output=True, text=True, timeout=90)
        return r.returncode == 0, (r.stdout.strip().splitlines() or [''])[-1]
    if acao in ('navegador', 'loja', 'cinema'):   # navegador do PS2 (navegador/): sistema-mobile-3004, loja ou cinema
        subprocess.run(['pm2', 'start', 'ps2-navegador'], capture_output=True, timeout=30)
        for _ in range(20):   # o servidor do navegador pode estar subindo
            try:
                with socket.create_connection((os.environ.get('PS2_NAV_IP', '127.0.0.1'), 8772), timeout=2) as c:
                    c.sendall({'loja': b'loja\n', 'cinema': b'cinema\n'}.get(acao, b'sistema\n'))
                    c.recv(8)
                break
            except OSError:
                time.sleep(1)
        with _trava_ps2:
            r = subprocess.run([os.path.expanduser('~/.local/bin/ps2-navegador.sh')], capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout.strip().splitlines() or [''])[-1]
    cmd = {'reiniciar': 'reset', 'desligar': 'poweroff'}.get(acao)
    if not cmd:
        return False, 'ação desconhecida'
    with _trava_ps2:
        subprocess.run([os.path.expanduser('~/.local/bin/ps2-fechar-navegador.sh')], capture_output=True, timeout=40)
        if not ping(PS2LINK):
            return False, 'O PS2 não responde na rede (desligado, num jogo ou no OPL). Só funciona com o PS2Link aberto.'
        if porta_aberta(PS2LINK, 21):
            return False, 'O PS2 está no wLaunchELF, não no PS2Link. Abra OPL → Apps → PS2Link.'
        if estatisticas._dados.get('atual'):   # o PS2Link não tem porta TCP para conferir; jogo aberto = sem PS2Link
            return False, 'Há um jogo aberto no PS2: o PS2Link não está rodando.'
        subprocess.run([os.path.expanduser('~/.local/bin/ps2client'), '-h', PS2LINK, '-t', '3', cmd],
                       capture_output=True, timeout=15)
        time.sleep(4)
        if acao == 'desligar':
            ok = not ping(PS2LINK)
            return ok, 'PS2 desligado.' if ok else 'Comando enviado, mas o PS2 ainda responde.'
        return True, 'PS2 reiniciado: volta ao PS2Link em alguns segundos.'


def ftp_no_ar():
    try:
        socket.create_connection((PS2_FTP, 21), timeout=2).close()
        return True
    except OSError:
        return False


def baixar_capa(jid):
    destino = os.path.join(CAPAS, jid + '.jpg')
    if os.path.exists(destino):
        return
    tmp = destino + '.tmp'
    subprocess.run(['smbclient', f'//{TVBOX}/PS2', '-N', '-m', 'NT1', '--option=client min protocol=NT1',
                    '-c', f'get ART/{jid}_COV.jpg {tmp}'], capture_output=True, timeout=30)
    if not (os.path.exists(tmp) and os.path.getsize(tmp) > 0):
        url = ('https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/default/'
               + jid.replace('_', '-').replace('.', '') + '.jpg')
        try:
            with urllib.request.urlopen(url, timeout=20) as r, open(tmp, 'wb') as f:
                f.write(r.read())
        except Exception:
            pass
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, destino)
    elif os.path.exists(tmp):
        os.remove(tmp)


def jogos():
    with _trava:
        if time.time() - _cache['t'] > 300 or not _cache['jogos']:
            saida = subprocess.run([SCRIPT, '--lista'], capture_output=True, text=True, timeout=60).stdout
            lista = [dict(zip(('id', 'nome'), l.split('\t', 1))) for l in saida.splitlines() if '\t' in l]
            _cache.update(t=time.time(), jogos=lista)
            faltam = [j['id'] for j in lista if not os.path.exists(os.path.join(CAPAS, j['id'] + '.jpg'))]
            threading.Thread(target=lambda: [baixar_capa(i) for i in faltam], daemon=True).start()
    return [dict(j, capa=f"capas/{j['id']}.jpg" if os.path.exists(os.path.join(CAPAS, j['id'] + '.jpg')) else '')
            for j in _cache['jogos']]


class Pagina(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=PASTA, **k)

    def log_message(self, *a):
        pass

    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def local(self):
        """Só a rede de casa mexe nas chaves (o painel não sai para a internet, mas por garantia)."""
        ip = self.client_address[0]
        return ip.startswith(('127.', '192.168.', '10.', '::1', '::ffff:127.', '::ffff:192.168.'))

    def do_GET(self):
        if self.path.startswith('/api/chaves'):
            return self._json(chaves.listar()) if self.local() else self._json({'erro': 'só da rede de casa'}, 403)
        if self.path.startswith('/api/athena-resultado'):   # teste de rede do AthenaEnv no PS2 (athena-teste/main.js)
            from urllib.parse import urlparse, parse_qs
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            esperado = open(os.path.join(PASTA, 'athena', 'teste.esperado')).read().split()
            q['integro'] = str(q.get('len') == esperado[0] and q.get('fnv') == esperado[1])
            with open(os.path.join(PASTA, 'athena', 'resultado.log'), 'a') as f:
                f.write(time.strftime('%d/%m %H:%M:%S ') + json.dumps(q) + '\n')
            return self._json({'ok': True})
        if self.path.startswith('/api/estatisticas'):
            return self._json(estatisticas.resumo(jogos()))
        if self.path.startswith('/api/ps2/temperatura'):
            return self._json(temperatura.atual())
        if self.path.startswith('/api/cinema/'):   # Jellyfin e TV ao vivo no PS2 (cinema.py)
            partes = self.path.split('?')[0].split('/')
            try:
                if partes[3] == 'inicio':
                    return self._json(cinema.inicio())
                if partes[3] == 'baixados':
                    return self._json(cinema.baixados())
                if partes[3] == 'serie':
                    return self._json(cinema.serie(partes[4]))
                if partes[3] == 'img':
                    arq = cinema.imagem(partes[4])
                    if not arq:
                        return self._json({'erro': 'sem imagem'}, 404)
                    corpo = open(arq, 'rb').read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Cache-Control', 'max-age=86400')
                    self.send_header('Content-Length', str(len(corpo)))
                    self.end_headers()
                    self.wfile.write(corpo)
                    return
            except Exception as e:
                return self._json({'erro': str(e)}, 500)
            return self._json({'erro': 'não encontrado'}, 404)
        if self.path.startswith('/api/loja/snes'):
            return self._json(snes())
        if self.path.startswith('/api/loja'):
            dados = loja.catalogo()
            tempos = {j['id']: j['segundos'] for j in estatisticas.resumo([])['jogos']}
            for j in dados['jogos']:
                j['jogado_s'] = tempos.get(j['id'], 0)
            return self._json(dados)
        if self.path.startswith('/api/jogos'):
            return self._json(jogos())
        if self.path.startswith('/api/proximo'):
            if not ftp_no_ar():
                return self._json({'ftp': False})
            try:
                with urllib.request.urlopen(f'ftp://{PS2_FTP}/mc/0/OPL/conf_last.cfg', timeout=10) as r:
                    atual = r.read().decode(errors='ignore').strip().split('=', 1)[-1]
            except Exception:
                atual = ''
            return self._json({'ftp': True, 'id': atual})
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/chaves/'):
            if not self.local():
                return self._json({'erro': 'só da rede de casa'}, 403)
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
            except ValueError:
                corpo = {}
            acao = self.path.split('?')[0].split('/')[3]
            if acao == 'criar':
                ok, r = chaves.criar(corpo.get('nome'), corpo.get('dias'))
                return self._json({'ok': ok, 'chave': r} if ok else {'ok': False, 'msg': r})
            ok, msg = chaves.mudar(str(corpo.get('id', '')), acao)
            return self._json({'ok': ok, 'msg': msg})
        if self.path.startswith('/api/ps2/temperatura'):   # loja nativa (AthenaEnv) no PS2
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
            except ValueError:
                corpo = {}
            return self._json({'ok': temperatura.registrar(corpo.get('c'), str(corpo.get('origem', 'ps2'))[:20])})
        if self.path.startswith('/api/cinema/'):
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
            except ValueError:
                corpo = {}
            acao = self.path.split('?')[0].split('/')[3]
            try:
                if acao == 'tocar':
                    ok, msg = cinema.tocar(item_id=corpo.get('id'), canal_id=corpo.get('canal'),
                                           inicio_s=int(corpo.get('inicio') or 0))
                elif acao == 'pular':
                    ok, msg = cinema.pular(int(corpo.get('seg', 30)), float(corpo.get('pos', 0)))
                elif acao == 'parado':
                    ok, msg = cinema.parado(float(corpo.get('pos', 0)))
                elif acao == 'baixar':
                    ok, msg = cinema.baixar(corpo.get('id'))
                elif acao == 'apagar':
                    ok, msg = cinema.apagar(corpo.get('slug', ''))
                else:
                    return self._json({'ok': False, 'msg': 'ação desconhecida'}, 404)
            except Exception as e:
                ok, msg = False, f'erro: {e}'
            return self._json({'ok': ok, 'msg': msg})
        if self.path.startswith('/api/loja/snes'):   # ROM → pendrive do PS2 (o navegador.elf grava)
            try:
                arq = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}').get('arquivo', '')
            except ValueError:
                arq = ''
            if self.path.startswith('/api/loja/snes/tvbox-retroarch'):   # RetroArch → pendrive da TV box (Samba do OPL)
                ok, msg = loja.instalar_retroarch_tvbox(RA_DIR, RA_ELF)
                return self._json({'ok': ok, 'msg': msg})
            if self.path.startswith('/api/loja/snes/retroarch'):   # passo 1: RetroArch → pendrive do PS2
                r = controle_navegador('retroarch')
                return self._json({'ok': r == 'ok', 'msg': 'Instalando o SNESticle no pendrive do PS2…' if r == 'ok' else (r or 'navegador fora do ar')})
            if self.path.startswith('/api/loja/snes/atualizar-retroarch'):   # o SNESticle é compilado aqui (~/ps2-monitor/snesticle)
                ok, msg = False, 'O SNESticle da loja é compilado no notebook (~/ps2-monitor/snesticle), não baixado.'
                return self._json({'ok': ok, 'msg': msg})
            if not arq or not os.path.isfile(os.path.join(SNES, os.path.basename(arq))):
                return self._json({'ok': False, 'msg': 'ROM não encontrada'}, 400)
            if self.path.startswith('/api/loja/snes/jogar'):
                ok, msg = jogar_snes(os.path.basename(arq))
                return self._json({'ok': ok, 'msg': msg})
            r = controle_navegador('copiar ' + os.path.basename(arq))
            return self._json({'ok': r == 'ok', 'msg': 'Gravando no pendrive do PS2…' if r == 'ok' else (r or 'navegador fora do ar')})
        if self.path.startswith('/api/loja/'):
            try:
                arq = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}').get('arquivo', '')
            except ValueError:
                arq = ''
            acao = {'instalar': loja.instalar, 'desinstalar': loja.desinstalar,
                    'cancelar': loja.cancelar}.get(self.path.split('/')[3].split('?')[0])
            if not acao or not arq:
                return self._json({'ok': False, 'msg': 'pedido inválido'}, 400)
            ok, msg = acao(os.path.basename(arq))
            return self._json({'ok': ok, 'msg': msg})
        if self.path.startswith('/api/jogar') or self.path.startswith('/api/sistema'):
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
            except ValueError:
                corpo = {}
            if self.path.startswith('/api/sistema'):
                ok, msg = sistema(corpo.get('acao', ''))
                return self._json({'ok': ok, 'msg': msg})
            # caminho 2: PS2 no PS2Link → Neutrino lê o ISO pelo servidor udpfs (ps2-jogar.sh)
            jid = corpo.get('id', '')
            if not jid or jid not in {j['id'] for j in _cache['jogos']}:
                return self._json({'ok': False, 'msg': 'jogo desconhecido'}, 400)
            ok, msg, _ = jogar(jid)
            return self._json({'ok': ok, 'msg': msg})
        if not self.path.startswith('/api/proximo'):
            return self._json({'erro': 'não encontrado'}, 404)
        try:
            jid = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}').get('id', '')
        except ValueError:
            jid = ''
        if not jid or jid not in {j['id'] for j in _cache['jogos']}:
            return self._json({'ok': False, 'msg': 'jogo desconhecido'}, 400)
        r = subprocess.run([SCRIPT, jid], capture_output=True, text=True, timeout=60)
        return self._json({'ok': r.returncode == 0, 'msg': (r.stdout or r.stderr).strip()})


import chaves, cinema, estatisticas, loja, painel_ha, temperatura, voz  # noqa: E402  (usam jogos/jogar/sistema daqui)

_baixando = set()


def capa_loja(jid):
    """Caminho da capa para a loja; se faltar, baixa em segundo plano (aparece na próxima atualização)."""
    if os.path.exists(os.path.join(CAPAS, jid + '.jpg')):
        return f'capas/{jid}.jpg'
    if jid not in _baixando:
        _baixando.add(jid)
        threading.Thread(target=baixar_capa, args=(jid,), daemon=True).start()
    return ''


SNES = os.path.join(PASTA, 'navegador', 'ps2', 'snes')   # ROMs de SNES (link para 01TERA/PS2/SNES, extraídas do ISO do emulador)


def controle_navegador(pedido, espera=5):
    try:
        with socket.create_connection((os.environ.get('PS2_NAV_IP', '127.0.0.1'), 8772), timeout=espera) as c:
            c.sendall(pedido.encode() + b'\n')
            return c.recv(4096).decode(errors='ignore').strip()
    except OSError:
        return ''


def snes():
    try:
        estado = json.loads(controle_navegador('pedido') or '{}')
    except ValueError:
        estado = {}
    atual, resultados = estado.get('atual') or {}, estado.get('resultados') or {}
    roms = []
    for f in sorted(os.listdir(SNES), key=str.lower):
        if f.lower().endswith(('.smc', '.sfc')):
            base = f.rsplit('.', 1)[0]
            capa = f'capas/snes/{base}.jpg'
            if atual.get('arquivo') == f:
                ped = {'fase': atual.get('fase'), 'estado': atual.get('estado') or 'na fila', 'pct': atual.get('pct', 0),
                       'andamento': True}
            else:
                ped = resultados.get(f, {})
            roms.append({'arquivo': f, 'nome': base, 'tamanho': os.path.getsize(os.path.join(SNES, f)),
                         'capa': capa if os.path.exists(os.path.join(PASTA, capa)) else '', 'pedido': ped})
    ra = {'pedido': resultados.get('__retroarch__', {}), 'versao': versao_ra(),
          'tamanho': os.path.getsize(os.path.join(RA_DIR, RA_ELF)),
          'na_tvbox': loja.retroarch_na_tvbox(RA_DIR, RA_ELF)}
    if atual.get('arquivo') == '__retroarch__':
        ra['pedido'] = {'fase': atual.get('fase'), 'estado': atual.get('estado') or 'na fila', 'pct': atual.get('pct', 0),
                        'andamento': True}
    return {'roms': roms, 'retroarch': ra, 'navegador': controle_navegador('status') == 'aberto'}


RA_DIR = os.path.join(PASTA, 'navegador', 'ps2', 'snesticle')   # SNESticle Revive (ORIGEM.txt); era o RetroArch
RA_ELF = 'SNESticle.elf'
RA_URL = 'https://buildbot.libretro.com/nightly/playstation/ps2/latest/snes9x2002_libretro_ps2.elf.zip'


def versao_ra():
    try:
        return time.strftime('%d/%m/%Y', time.localtime(os.path.getmtime(os.path.join(RA_DIR, RA_ELF))))
    except OSError:
        return ''


def atualizar_ra():
    """Baixa o RetroArch PS2 (núcleo snes9x2002) mais novo do buildbot oficial do libretro para o notebook."""
    import io, zipfile
    try:
        with urllib.request.urlopen(RA_URL, timeout=120) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        elf = z.read('snes9x2002_libretro_ps2.elf')
    except Exception as e:
        return False, f'não consegui baixar do site oficial: {e}'
    if elf[:4] != b'\x7fELF' or len(elf) < 500000:
        return False, 'o arquivo baixado não parece o RetroArch PS2'
    destino = os.path.join(RA_DIR, RA_ELF)
    with open(destino + '.tmp', 'wb') as f:
        f.write(elf)
    os.replace(destino + '.tmp', destino)
    with open(os.path.join(RA_DIR, 'ORIGEM.txt'), 'w') as f:
        f.write(f'RetroArch PS2 nightly (núcleo snes9x2002) baixado de {RA_URL} em {time.strftime("%d/%m/%Y %H:%M")}.\n'
                'Vai para mass:/APPS/RETROARCH no pendrive do PS2 (Instalar na loja).\n')
    return True, f'RetroArch atualizado ({len(elf) // 1024} KB). Agora instale no pendrive do PS2.'


def jogar_snes(nome):
    """▶ Jogar SNES: SNESticle do pendrive do PS2 com a ROM do pendrive. Com o navegador aberto no PS2 ele mesmo
    abre (pedido "jogar"); senão, com o PS2 no PS2Link, o ps2client manda o SNESticle (do notebook) com a ROM do pendrive."""
    if controle_navegador('status') == 'aberto':
        r = controle_navegador('jogar ' + nome)
        return r == 'ok', 'Abrindo no PS2…' if r == 'ok' else r
    with _trava_ps2:
        if not ping(PS2LINK) or porta_aberta(PS2LINK, 21):
            return False, 'Abra o PS2Link no PS2 (OPL → Apps → PS2Link) ou a loja no PS2.'
        pasta = os.path.join(PASTA, 'navegador', 'ps2')
        subprocess.Popen(['ps2client', '-h', PS2LINK, 'execee', 'host:snesticle/' + RA_ELF,
                          f'mass:/SNES/{nome}'], cwd=pasta, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        time.sleep(3)
    return True, 'SNESticle enviado ao PS2 (a ROM precisa estar no pendrive do PS2).'


def jogando_agora():
    a = estatisticas._dados.get('atual')
    return a and a.get('id')

if __name__ == '__main__':
    os.makedirs(CAPAS, exist_ok=True)
    estatisticas.iniciar()
    loja.iniciar(capa_loja, lambda: _cache.update(t=0), jogando_agora)
    voz.iniciar(jogos, jogar, sistema)
    painel_ha.iniciar(jogos, jogar, sistema, _trava_ps2)
    ThreadingHTTPServer(('0.0.0.0', 8770), Pagina).serve_forever()
