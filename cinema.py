"""Cinema no PS2 (pedido do usuário 17/10/2026: "faça 1 e 2" = Jellyfin e TV ao vivo no PS2).

Interface (cinema.html, aberta no navegador do PS2) + conversão para o que o PS2 toca por hardware:
  vídeo MPEG-2 elementar 640x400 (o IPU do PS2 decodifica; letterbox para 16:9;
  640x448 passa de 1023 macroblocos e o libmpeg do ps2sdk trava na conversão de cor em duas partes), áudio PCM 16 bits estéreo 22050 Hz,
  legenda PT-BR gravada na imagem. Os dois arquivos crescem enquanto o ffmpeg converte; o navegador.elf lê pelo host:
  do PS2Link (pasta navegador/ps2/video → /mnt/500gb/ps2-video) e toca em sincronia (o áudio manda no relógio).
Fontes: Jellyfin (usuário Rodrigo) e canais da ponte Rede Canais (8099) + Pluto/Plex da fast-tv (8097).
"""
import glob, io, json, os, re, signal, socket, subprocess, threading, time, urllib.parse, urllib.request

from PIL import Image

PASTA = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(PASTA, 'navegador', 'ps2', 'video')
CAPAS = os.path.join(PASTA, 'capas', 'jf')
JF = 'http://127.0.0.1:8096'
USUARIO = '620244e51a7d439892bcaa337b02e298'   # "Rodrigo" (o que tem "continuar assistindo")
FFMPEG = '/usr/lib/jellyfin-ffmpeg/ffmpeg'
LISTAS = [('Rede Canais', 'http://127.0.0.1:8099/lista.m3u'), ('Pluto TV', 'http://127.0.0.1:8097/pluto.m3u'),
          ('Plex', 'http://127.0.0.1:8097/plex.m3u')]
AUDIO_HZ = 22050
_estado = {'proc': None, 'sessao': None, 'item': None, 'inicio': 0, 'titulo': '', 'canal': None}
_trava = threading.Lock()
_canais_cache = {'t': 0, 'lista': []}


def _chave():
    for linha in open(os.path.expanduser('~/.env')):
        if linha.startswith('JELLYFIN_API_KEY='):
            return linha.strip().split('=', 1)[1].strip('"\'')
    return ''


CHAVE = _chave()


def jf(caminho, **q):
    q = {k: v for k, v in q.items() if v is not None}
    url = JF + caminho + ('?' + urllib.parse.urlencode(q) if q else '')
    req = urllib.request.Request(url, headers={'X-Emby-Token': CHAVE})
    return json.load(urllib.request.urlopen(req, timeout=20))


def _resumo(i):
    tipo = i.get('Type')
    nome = i.get('Name', '')
    if tipo == 'Episode':
        nome = f"{i.get('SeriesName', '')} T{i.get('ParentIndexNumber', 0)}E{i.get('IndexNumber', 0):02d} · {nome}"
    ud = i.get('UserData') or {}
    dur = (i.get('RunTimeTicks') or 0) / 1e7
    return {'id': i['Id'], 'tipo': tipo, 'nome': nome, 'ano': i.get('ProductionYear'),
            'sinopse': (i.get('Overview') or '')[:400], 'duracao': int(dur),
            'assistido': ud.get('Played', False), 'posicao': int((ud.get('PlaybackPositionTicks') or 0) / 1e7),
            'capa': f"api/cinema/img/{i.get('SeriesId') if tipo == 'Episode' and not i.get('ImageTags', {}).get('Primary') else i['Id']}"}


def inicio():
    campos = 'Overview,UserData,RunTimeTicks,ProductionYear'
    cont = jf(f'/Users/{USUARIO}/Items/Resume', Limit=20, Fields=campos, MediaTypes='Video')['Items']
    series = jf(f'/Users/{USUARIO}/Items', IncludeItemTypes='Series', Recursive='true', SortBy='DateLastContentAdded',
                SortOrder='Descending', Limit=40, Fields=campos)['Items']
    filmes = jf(f'/Users/{USUARIO}/Items', IncludeItemTypes='Movie', Recursive='true', SortBy='DateCreated',
                SortOrder='Descending', Limit=40, Fields=campos)['Items']
    return {'continuar': [_resumo(i) for i in cont], 'series': [_resumo(i) for i in series],
            'filmes': [_resumo(i) for i in filmes], 'canais': canais()}


def serie(sid):
    campos = 'Overview,UserData,RunTimeTicks'
    eps = jf(f'/Shows/{sid}/Episodes', UserId=USUARIO, Fields=campos)['Items']
    temporadas = {}
    for e in eps:
        temporadas.setdefault(e.get('ParentIndexNumber', 0), []).append(_resumo(e))
    info = jf(f'/Users/{USUARIO}/Items/{sid}')
    return {'id': sid, 'nome': info.get('Name'), 'sinopse': info.get('Overview', ''), 'capa': f'api/cinema/img/{sid}',
            'temporadas': [{'numero': k, 'episodios': v} for k, v in sorted(temporadas.items())]}


def canais():
    if time.time() - _canais_cache['t'] < 600 and _canais_cache['lista']:
        return _canais_cache['lista']
    lista = []
    for grupo, url in LISTAS:
        try:
            texto = urllib.request.urlopen(url, timeout=15).read().decode('utf-8', 'replace')
        except Exception:
            continue
        info = None
        for linha in texto.splitlines():
            if linha.startswith('#EXTINF'):
                logo = re.search(r'tvg-logo="([^"]*)"', linha)
                info = {'nome': linha.rsplit(',', 1)[-1].strip(), 'logo': logo.group(1) if logo else '', 'grupo': grupo}
            elif linha.startswith('http') and info:
                info['url'] = linha.strip()
                info['id'] = 'tv-' + re.sub(r'[^a-z0-9]+', '-', (grupo + '-' + info['nome']).lower()).strip('-')
                info['capa'] = f"api/cinema/img/{info['id']}"
                lista.append(info)
                info = None
    _canais_cache.update(t=time.time(), lista=lista)
    return lista


def imagem(iid):
    """Capa pequena em JPEG (cache em capas/jf): Jellyfin ou logo do canal."""
    iid = re.sub(r'[^A-Za-z0-9-]', '', iid)
    destino = os.path.join(CAPAS, iid + '.jpg')
    if not os.path.exists(destino):
        try:
            if iid.startswith('tv-'):
                c = next(c for c in canais() if c['id'] == iid)
                dados = urllib.request.urlopen(urllib.request.Request(c['logo'], headers={'User-Agent': 'Mozilla/5.0'}),
                                               timeout=15).read()
                fundo = Image.new('RGB', (200, 150), (24, 30, 48))
                logo = Image.open(io.BytesIO(dados)).convert('RGBA')
                logo.thumbnail((170, 120))
                fundo.paste(logo, ((200 - logo.width) // 2, (150 - logo.height) // 2), logo)
                fundo.save(destino, 'JPEG', quality=85)
            else:
                dados = urllib.request.urlopen(urllib.request.Request(
                    f'{JF}/Items/{iid}/Images/Primary?maxWidth=200&quality=80', headers={'X-Emby-Token': CHAVE}), timeout=15).read()
                Image.open(io.BytesIO(dados)).convert('RGB').save(destino, 'JPEG', quality=85)
        except Exception:
            return None
    return destino


# ---------------- conversão para o PS2 ----------------
def _legenda(caminho, fluxos):
    """(filtro de legenda PT-BR ou '', descrição). Externa .pt-BR/.por/.pt ao lado do arquivo, senão embutida em português."""
    base = os.path.splitext(caminho)[0]
    for suf in ('.pt-BR.srt', '.pt-br.srt', '.por.srt', '.pt.srt', '.pt-BR.ass', '.por.ass'):
        if os.path.exists(base + suf):
            return 'subtitles=' + _esc(base + suf) + ":force_style='FontSize=24,Outline=2'", 'externa'
    textos = [s for s in fluxos if s.get('Type') == 'Subtitle' and not s.get('IsExternal')
              and (s.get('Codec') or '').lower() in ('subrip', 'srt', 'ass', 'ssa', 'mov_text')]
    for n, s in enumerate(textos):
        if (s.get('Language') or '').lower() in ('por', 'pt', 'pt-br', 'pob'):
            return f"subtitles={_esc(caminho)}:si={n}:force_style='FontSize=24,Outline=2'", 'embutida'
    return '', 'sem legenda'


def _esc(p):   # caminho dentro de um filtro do ffmpeg
    return "'" + p.replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:') + "'"


def _parar_ffmpeg():
    p = _estado['proc']
    if p and p.poll() is None:
        p.send_signal(signal.SIGTERM)
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
    _estado['proc'] = None


def _limpar_antigos():
    for f in glob.glob(os.path.join(VIDEO, 's*')):
        if _estado['sessao'] and os.path.basename(f).startswith(_estado['sessao']):
            continue
        try:
            os.remove(f)
        except OSError:
            pass


def _navegador(pedido):
    try:
        with socket.create_connection((os.environ.get('PS2_NAV_IP', '127.0.0.1'), 8772), timeout=5) as c:
            c.sendall(pedido.encode() + b'\n')
            return c.recv(256).decode(errors='ignore').strip()
    except OSError:
        return ''


def tocar(item_id=None, canal_id=None, inicio_s=0):
    """Começa a conversão e manda o PS2 entrar no modo vídeo. Devolve (ok, mensagem)."""
    with _trava:
        _parar_ffmpeg()
        sessao = 's%d' % int(time.time() * 10 % 10**9)
        _estado.update(sessao=sessao)
        _limpar_antigos()
        v, a = os.path.join(VIDEO, sessao + '.m2v'), os.path.join(VIDEO, sessao + '.pcm')
        filtro = 'scale=640:400:force_original_aspect_ratio=decrease,pad=640:400:(ow-iw)/2:(oh-ih)/2,setsar=1'
        entrada, extra_in, mapa_a, titulo, desc_leg = None, [], '0:a:0?', '', ''
        if canal_id:
            c = next((c for c in canais() if c['id'] == canal_id), None)
            if not c:
                return False, 'canal não encontrado'
            entrada, titulo = c['url'], c['nome']
            extra_in = ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5', '-rw_timeout', '15000000']
            inicio_s = 0
            _estado.update(item=None, canal=canal_id)
        else:
            i = jf(f'/Users/{USUARIO}/Items/{item_id}', Fields='Path,MediaStreams')
            entrada, fluxos = i.get('Path'), i.get('MediaStreams') or []
            titulo = _resumo(i)['nome']
            audios = [s for s in fluxos if s.get('Type') == 'Audio']
            pt = [n for n, s in enumerate(audios) if (s.get('Language') or '').lower() in ('por', 'pt', 'pob', 'pt-br')]
            mapa_a = f'0:a:{pt[0] if pt else 0}?'
            if not pt:   # áudio estrangeiro: legenda PT-BR na imagem
                leg, desc_leg = _legenda(entrada, fluxos)
                if leg:   # com -ss antes do -i o tempo recomeça do zero: a legenda precisa do deslocamento
                    filtro += f',setpts=PTS+{inicio_s}/TB,{leg},setpts=PTS-STARTPTS'
            else:
                desc_leg = 'áudio em português'
            _estado.update(item=item_id, canal=None)
        cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin']
        if inicio_s:
            cmd += ['-ss', str(int(inicio_s))]
        cmd += extra_in + ['-i', entrada,
                           '-map', '0:v:0', '-vf', filtro, '-r', '30000/1001', '-c:v', 'mpeg2video', '-b:v', '2200k',
                           '-maxrate', '3500k', '-bufsize', '1835k', '-g', '15', '-bf', '2', '-threads', '6',
                           '-f', 'mpeg2video', v,
                           '-map', mapa_a, '-ac', '2', '-ar', str(AUDIO_HZ), '-c:a', 'pcm_s16le', '-f', 's16le', a]
        log = open(os.path.join(VIDEO, sessao + '.log'), 'w')
        _estado['proc'] = subprocess.Popen(cmd, stdout=log, stderr=log)
        _estado.update(inicio=inicio_s, titulo=titulo)
        json.dump({'titulo': titulo, 'inicio': inicio_s, 'legenda': desc_leg}, open(os.path.join(VIDEO, sessao + '.json'), 'w'),
                  ensure_ascii=False)
        threading.Thread(target=_vigiar, args=(_estado['proc'], sessao), daemon=True).start()
    # espera ter um pouco de vídeo antes de chamar o PS2 (até 20 s)
    for _ in range(80):
        if os.path.exists(v) and os.path.getsize(v) > 400_000 and os.path.exists(a) and os.path.getsize(a) > 200_000:
            break
        if _estado['proc'] is None or _estado['proc'].poll() is not None:
            erro = open(os.path.join(VIDEO, sessao + '.log')).read()[-300:]
            return False, 'a conversão falhou: ' + (erro or 'sem detalhes')
        time.sleep(0.25)
    r = _navegador(f'video {sessao}')
    if r != 'ok':
        return False, 'o navegador não está aberto no PS2' if not r else r
    return True, f'Abrindo "{titulo}" no PS2 ({desc_leg or "ao vivo"})'


def _vigiar(proc, sessao):
    proc.wait()
    open(os.path.join(VIDEO, sessao + '.fim'), 'w').close()   # o PS2 sabe que acabou (não é só a conversão atrasada)


def pular(segundos, posicao_ps2_s):
    """← → no controle: recomeça a conversão alguns segundos para frente/trás (só para itens do Jellyfin)."""
    if not _estado['item']:
        return False, 'ao vivo não volta'
    novo = max(0, int(_estado['inicio'] + posicao_ps2_s + segundos))
    return tocar(item_id=_estado['item'], inicio_s=novo)


def parado(posicao_ps2_s):
    """O PS2 saiu do modo vídeo: para a conversão e grava em que ponto parou no Jellyfin."""
    with _trava:
        _parar_ffmpeg()
    item, pos = _estado['item'], _estado['inicio'] + posicao_ps2_s
    if item and pos > 30:   # grava no Jellyfin onde parou (ou marca como assistido perto do fim)
        try:
            dur = (jf(f'/Users/{USUARIO}/Items/{item}').get('RunTimeTicks') or 0) / 1e7
            dados = {'Played': True, 'PlaybackPositionTicks': 0} if dur and pos > dur * 0.92 else \
                {'PlaybackPositionTicks': int(pos * 1e7), 'LastPlayedDate': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            req = urllib.request.Request(f'{JF}/UserItems/{item}/UserData?userId={USUARIO}', data=json.dumps(dados).encode(),
                                         method='POST', headers={'X-Emby-Token': CHAVE, 'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass
    _estado.update(item=None, canal=None)
    return True, 'parado'


# ---------------- baixar para ver depois (pendrive do PS2, assistido pelo SMS sem notebook) ----------------
# O notebook converte o episódio inteiro para o que o SMS toca (AVI XviD ≤ 720 px + MP3, legenda PT-BR na imagem),
# depois o navegador do PS2 copia para mass:/CINEMA no pendrive (cópia em segundo plano, a tela não para).
BAIXAR = os.path.join(VIDEO, 'baixar')
REGISTRO = os.path.join(PASTA, 'cinema_baixados.json')
_baixados = {}
_fila_conv = []
_trava_b = threading.Lock()


def _salvar_registro():
    with open(REGISTRO + '.tmp', 'w') as f:
        json.dump(_baixados, f, ensure_ascii=False, indent=1)
    os.replace(REGISTRO + '.tmp', REGISTRO)


def _slug(nome):
    import unicodedata
    t = unicodedata.normalize('NFD', nome)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[^A-Za-z0-9 ._-]+', '', t).strip()
    return re.sub(r'\s+', ' ', t)[:60] or 'video'


def baixar(item_id):
    i = jf(f'/Users/{USUARIO}/Items/{item_id}', Fields='Path,MediaStreams')
    nome = _resumo(i)['nome']
    slug = _slug(nome)
    with _trava_b:
        if slug in _baixados and _baixados[slug]['estado'] not in ('erro',):
            return True, 'Já está na lista de baixados.'
        _baixados[slug] = {'titulo': nome, 'item': item_id, 'estado': 'na fila', 'pct': 0, 't': time.time(),
                           'arquivo': f'mass:/CINEMA/{slug}.avi', 'tamanho': 0}
        _fila_conv.append(slug)
        _salvar_registro()
    return True, f'"{nome}" entrou na fila: o notebook converte e depois o PS2 grava no pendrive.'


def _converter(slug):
    b = _baixados[slug]
    i = jf(f'/Users/{USUARIO}/Items/{b["item"]}', Fields='Path,MediaStreams')
    entrada, fluxos = i['Path'], i.get('MediaStreams') or []
    dur = (i.get('RunTimeTicks') or 0) / 1e7
    audios = [s for s in fluxos if s.get('Type') == 'Audio']
    pt = [n for n, s in enumerate(audios) if (s.get('Language') or '').lower() in ('por', 'pt', 'pob', 'pt-br')]
    filtro = 'scale=640:-2'
    if not pt:
        leg, _ = _legenda(entrada, fluxos)
        if leg:
            filtro += ',' + leg
    os.makedirs(BAIXAR, exist_ok=True)
    saida = os.path.join(BAIXAR, slug + '.avi')
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', entrada, '-map', '0:v:0',
           '-map', f'0:a:{pt[0] if pt else 0}?', '-vf', filtro, '-r', '30000/1001', '-c:v', 'mpeg4', '-vtag', 'XVID',
           '-b:v', '1200k', '-maxrate', '2000k', '-bufsize', '2000k', '-g', '250', '-bf', '0',
           '-c:a', 'libmp3lame', '-b:a', '128k', '-ac', '2', '-ar', '44100', '-threads', '6',
           '-progress', 'pipe:1', '-f', 'avi', saida + '.tmp']
    b.update(estado='convertendo', pct=0)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for linha in p.stdout:
        if linha.startswith('out_time_ms=') and dur:
            try:
                b['pct'] = min(99, int(int(linha.split('=')[1]) / 1e6 / dur * 100))
            except ValueError:
                pass
    p.wait()
    if p.returncode != 0 or not os.path.exists(saida + '.tmp'):
        b.update(estado='erro', msg='a conversão falhou: ' + p.stderr.read()[-200:])
        return
    os.replace(saida + '.tmp', saida)
    b.update(estado='convertido', pct=100, tamanho=os.path.getsize(saida))


def _laco_baixar():
    """Converte um por vez; quando o navegador estiver aberto no PS2, pede a cópia e acompanha até o fim."""
    try:
        _baixados.update(json.load(open(REGISTRO)))
    except (OSError, ValueError):
        pass
    for slug, b in _baixados.items():   # o notebook reiniciou no meio: retoma
        if b['estado'] in ('convertendo', 'na fila'):
            b['estado'] = 'na fila'
            _fila_conv.append(slug)
        if b['estado'] == 'copiando':
            b['estado'] = 'convertido'
    while True:
        try:
            slug = _fila_conv.pop(0) if _fila_conv else None
            if slug:
                _converter(slug)
                _salvar_registro()
            estado = json.loads(_navegador('pedido') or '{}')
            res = estado.get('resultados') or {}
            atual = estado.get('atual') or {}
            for s, b in list(_baixados.items()):
                rot = 'cinema:' + s
                if b['estado'] == 'convertido' and _navegador('status') == 'aberto' and not atual:
                    r = _navegador(f'copiar2 host:video/baixar/{s}.avi|{b["arquivo"]}|{rot}')
                    if r == 'ok':
                        b.update(estado='copiando', pct=0)
                        atual = {'arquivo': rot}
                elif b['estado'] == 'copiando':
                    if atual.get('arquivo') == rot:
                        b['pct'] = atual.get('pct', 0)
                    elif rot in res:
                        ok = res[rot].get('ok')
                        b.update(estado='no pendrive' if ok else 'erro', pct=100 if ok else 0,
                                 msg='' if ok else res[rot].get('estado', ''))
                        if ok:   # já está no pendrive: libera o HD do notebook
                            try:
                                os.remove(os.path.join(BAIXAR, s + '.avi'))
                            except OSError:
                                pass
                    elif _navegador('status') != 'aberto':
                        b['estado'] = 'convertido'   # o PS2 saiu no meio: copia de novo depois
                elif b['estado'] == 'apagando' and rot in res and res[rot].get('op') == 3:
                    del _baixados[s]
            _salvar_registro()
        except Exception as e:
            print('cinema baixar:', e, flush=True)
        time.sleep(3 if _fila_conv else 10)


def baixados():
    return [dict(b, slug=s) for s, b in sorted(_baixados.items(), key=lambda x: -x[1]['t'])]


def apagar(slug):
    b = _baixados.get(slug)
    if not b:
        return False, 'não encontrado'
    if b['estado'] != 'no pendrive':   # ainda não foi para o PS2: só tira da lista
        try:
            os.remove(os.path.join(BAIXAR, slug + '.avi'))
        except OSError:
            pass
        _baixados.pop(slug, None)
        if slug in _fila_conv:
            _fila_conv.remove(slug)
        _salvar_registro()
        return True, 'Removido da lista.'
    r = _navegador(f'apagar {b["arquivo"]}|cinema:{slug}')
    if r != 'ok':
        return False, 'para apagar do pendrive, abra o cinema no PS2'
    b['estado'] = 'apagando'
    _salvar_registro()
    return True, 'Apagando do pendrive…'


threading.Thread(target=_laco_baixar, daemon=True).start()
