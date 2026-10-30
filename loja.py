"""Loja de jogos do PS2 (pedido do usuário 16/10/2026: "monte a loja com os jogos do 01TERA").

Catálogo = ISOs de /media/rodrigo/01TERA/PS2/DVD (os jogos do próprio usuário). "Instalar" copia o ISO para o
pendrive da TV box (DVD/ do pendrive, que o OPL lê pelo Samba e o Neutrino pelo udpfs), com a capa em ART/.
"Desinstalar" apaga do pendrive só jogos que continuam no 01TERA com o mesmo tamanho (nada se perde).

Cópia: o Samba do Termux é só leitura e o adb push falha no FAT32 (fchown), então a TV box recebe por netcat
(adb shell nc -l -p 9771 > arquivo.part) e o notebook envia por TCP (~11 MB/s). Depois confere o tamanho e
3 trechos de 1 MB por MD5 e só então renomeia para .iso. Um jogo por vez; os outros ficam na fila.
"""
import hashlib, os, re, socket, subprocess, threading, time

# configurável (servidor/servidor.env, 18/10/2026): pasta da coleção (com DVD/ e CD/), IP da TV box e o pendrive dela
ORIGEM = os.path.join(os.environ.get('PS2_JOGOS', '/media/rodrigo/01TERA/PS2'), 'DVD')
TVBOX = os.environ.get('PS2_TVBOX', '192.168.4.79')
PEN = os.environ.get('PS2_TVBOX_USB', '/mnt/media_rw/1E0A-1F18')
ADB = ['adb', '-s', f'{TVBOX}:5555', 'shell']
PORTA_NC = 9771
FAT32_MAX = 4 * 1024 ** 3 - 1
FOLGA = 64 * 1024 ** 2

_estado = {}            # arquivo → {fase, feito, total, vel, msg, t}
_fila = []
_trava = threading.Lock()
_acordar = threading.Event()
_ganchos = {}           # funções do servidor.py: capa(jid), atualizou(), jogando()


def _sh(cmd, timeout=30):
    return subprocess.run(ADB + [cmd], capture_output=True, text=True, timeout=timeout).stdout


def id_nome(arquivo):
    base = re.sub(r'\.iso$', '', arquivo, flags=re.I)
    m = re.match(r'^([A-Z]{4}_\d{3}\.\d{2})\.(.*)$', base)
    return (m.group(1), m.group(2)) if m else ('', base)


def regiao(jid):
    p = jid[:4]
    if p.endswith('US') or p == 'SCUS':
        return 'EUA'
    if p.endswith('ES') or p in ('SCED',):
        return 'Europa'
    if p.endswith(('PM', 'PS', 'JM')) or p in ('SCPS', 'SCAJ', 'SCPM'):
        return 'Japão'
    return '—'


_pen_cache = {'isos': {}, 'livre': 0, 'total': 0}


def pendrive():
    """({arquivo: tamanho} dos ISOs no pendrive, livre_bytes, total_bytes, ok).

    Comparação de nomes SEM caixa (case-insensitive: FAT32 guarda como foi copiado, HD e pendrive
    podem diferir em maiúsculas/minúsculas do mesmo jogo).

    ok=False quando a TV box não responde (adb fora do ar): devolve a última leitura boa em cache,
    e a loja mostra "sem resposta" em vez de mentir com "0 livres / 0 instalados" (que levava a
    instalar o mesmo jogo de novo achando que o pendrive estava vazio).
    """
    try:
        saida = _sh(f'cd {PEN}/DVD && for f in *.iso *.ISO; do [ -f "$f" ] && echo "$(stat -c %s "$f")|$f"; done; '
                    f'echo "DF|$(df {PEN} | tail -1)"')
        isos, livre, total, achou_df = {}, 0, 0, False
        for linha in saida.splitlines():
            t, _, nome = linha.partition('|')
            if t == 'DF':
                p = nome.split()
                total, livre = int(p[1]) * 1024, int(p[3]) * 1024
                achou_df = True
            elif t.isdigit():
                isos[nome] = int(t)
        if not achou_df:
            raise RuntimeError('TV box sem resposta (sem espaço de disco no df).')
        _pen_cache.update(isos=dict(isos), livre=livre, total=total)
        return isos, livre, total, True
    except Exception:
        c = _pen_cache
        return dict(c['isos']), c['livre'], c['total'], False


def catalogo():
    no_pen, livre, total, ok = pendrive()
    no_pen_cx = {a.lower(): tam for a, tam in no_pen.items()}
    jogos = []
    nomes = set()
    for arq in sorted(os.listdir(ORIGEM) if os.path.isdir(ORIGEM) else [], key=str.lower):
        if not arq.lower().endswith('.iso'):
            continue
        caminho = os.path.join(ORIGEM, arq)
        st = os.stat(caminho)
        jid, nome = id_nome(arq)
        nomes.add(arq.lower())
        jogos.append({'arquivo': arq, 'id': jid, 'nome': nome, 'tamanho': st.st_size, 'novo': int(st.st_mtime),
                      'regiao': regiao(jid), 'instalado': no_pen_cx.get(arq.lower(), -1) == st.st_size,
                      'so_pendrive': False, 'cabe_fat32': st.st_size <= FAT32_MAX})
    for arq, tam in no_pen.items():   # jogos que só existem no pendrive (não dá para desinstalar)
        if arq.lower() not in nomes:
            jid, nome = id_nome(arq)
            jogos.append({'arquivo': arq, 'id': jid, 'nome': nome, 'tamanho': tam, 'novo': 0, 'regiao': regiao(jid),
                          'instalado': True, 'so_pendrive': True, 'cabe_fat32': True})
    jogos.sort(key=lambda j: j['arquivo'].lower())   # ✔ antes os "só pendrive" iam todos para o fim da lista
    for j in jogos:
        j['capa'] = _ganchos['capa'](j['id']) if j['id'] else ''
        j['estado'] = dict(_estado.get(j['arquivo'], {}))
    return {'jogos': jogos, 'livre': livre, 'total': total, 'box': ok, 'fila': list(_fila)}


# ---------------- instalar ----------------
def instalar(arq):
    caminho = os.path.join(ORIGEM, os.path.basename(arq))
    if not os.path.isfile(caminho):
        return False, 'Jogo não encontrado no 01TERA.'
    tam = os.path.getsize(caminho)
    if tam > FAT32_MAX:
        return False, 'Maior que 4 GB: não cabe no pendrive FAT32.'
    with _trava:
        if arq in _fila or _estado.get(arq, {}).get('fase') in ('copiando', 'conferindo'):
            return False, 'Já está na fila.'
        _fila.append(arq)
        _estado[arq] = {'fase': 'fila', 'feito': 0, 'total': tam, 'vel': 0, 'msg': 'Na fila', 't': time.time()}
    _acordar.set()
    return True, 'Adicionado à fila de instalação.'


def cancelar(arq):
    with _trava:
        if arq in _fila:
            _fila.remove(arq)
            _estado.pop(arq, None)
            return True, 'Removido da fila.'
        if _estado.get(arq, {}).get('fase') == 'copiando':
            _estado[arq]['cancelar'] = True
            return True, 'Cancelando…'
    return False, 'Não está instalando.'


def _md5_local(caminho, pos):
    with open(caminho, 'rb') as f:
        f.seek(pos)
        return hashlib.md5(f.read(1024 ** 2)).hexdigest()


def _copiar(arq):
    est = _estado[arq]
    origem = os.path.join(ORIGEM, arq)
    tam = os.path.getsize(origem)
    destino = f'{PEN}/DVD/{arq}'
    parte = f'{PEN}/DVD/.instalando.part'
    _, livre, _, _ = pendrive()
    if tam + FOLGA > livre:
        raise RuntimeError(f'Falta espaço no pendrive: precisa de {tam / 1024**3:.1f} GB, '
                           f'livre {livre / 1024**3:.1f} GB. Desinstale algum jogo.')
    _sh(f'rm -f "{parte}"; pkill -f "[n]c -l -p {PORTA_NC}" 2>/dev/null; true')
    receptor = subprocess.Popen(ADB + [f'nc -l -p {PORTA_NC} > "{parte}"'], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    try:
        for _ in range(20):
            try:
                s = socket.create_connection((TVBOX, PORTA_NC), timeout=2)
                s.settimeout(60)   # os 2 s eram só para conectar; o pendrive às vezes demora a gravar
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError('A TV box não abriu a porta de cópia.')
        est.update(fase='copiando', msg='Copiando')
        t0, feito = time.time(), 0
        with open(origem, 'rb') as f, s:
            while bloco := f.read(1024 ** 2):
                if est.get('cancelar'):
                    raise RuntimeError('Cancelado.')
                s.sendall(bloco)
                feito += len(bloco)
                dt = time.time() - t0
                est.update(feito=feito, vel=int(feito / dt) if dt > 0 else 0)
            s.shutdown(socket.SHUT_WR)
            s.settimeout(120)
            try:
                s.recv(1)
            except OSError:
                pass
        receptor.wait(timeout=120)
        est.update(fase='conferindo', msg='Conferindo')
        recebido = _sh(f'stat -c %s "{parte}"').strip()
        if recebido != str(tam):
            raise RuntimeError(f'Tamanho diferente depois da cópia ({recebido} de {tam}).')
        for pos in (0, tam // 2 // 1024 ** 2 * 1024 ** 2, max(0, (tam - 1) // 1024 ** 2 * 1024 ** 2)):
            remoto = _sh(f'dd if="{parte}" bs=1048576 skip={pos // 1024 ** 2} count=1 2>/dev/null | md5sum', 60).split()
            if not remoto or remoto[0] != _md5_local(origem, pos):
                raise RuntimeError('A conferência MD5 falhou: cópia corrompida.')
        _sh(f'mv "{parte}" "{destino}"')
        jid, _ = id_nome(arq)
        capa = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capas', jid + '.jpg')
        if jid and os.path.exists(capa) and not _sh(f'ls "{PEN}/ART/{jid}_COV.jpg" 2>/dev/null').strip():
            subprocess.run(['adb', '-s', f'{TVBOX}:5555', 'push', capa, '/data/local/tmp/capa.jpg'],
                           capture_output=True, timeout=30)
            _sh(f'mkdir -p "{PEN}/ART"; cp /data/local/tmp/capa.jpg "{PEN}/ART/{jid}_COV.jpg"; rm /data/local/tmp/capa.jpg')
        est.update(fase='pronto', msg='Instalado', feito=tam)
    except Exception:
        receptor.kill()
        _sh(f'rm -f "{parte}"; pkill -f "[n]c -l -p {PORTA_NC}" 2>/dev/null; true')
        raise


_ra_cache = {'t': 0, 'sim': False}


def retroarch_na_tvbox(ra_dir, elf_nome):
    """O emulador SNES do notebook (SNESticle) já está em APPS/SNESTICLE no pendrive da TV box? (cache de 30 s: a página consulta sempre)"""
    if time.time() - _ra_cache['t'] > 30:
        elf = os.path.join(ra_dir, elf_nome)
        try:
            remoto = _sh(f'stat -c %s "{PEN}/APPS/SNESTICLE/{elf_nome}" 2>/dev/null', 10).strip()
            _ra_cache.update(sim=remoto == str(os.path.getsize(elf)))
        except Exception:
            _ra_cache.update(sim=False)
        _ra_cache['t'] = time.time()
    return _ra_cache['sim']


def instalar_retroarch_tvbox(ra_dir, elf_nome):
    """Emulador SNES (SNESticle, ~5 MB; antes RetroArch) → APPS/SNESTICLE no pendrive da TV box (aparece no OPL → Apps pelo Samba), pedido do
    usuário 17/10/2026. adb push direto no FAT32 falha (fchown): vai para /data/local/tmp e depois cp, como as capas."""
    destino = f'{PEN}/APPS/SNESTICLE'
    try:
        _sh(f'mkdir -p "{destino}"')
        for nome in (elf_nome, 'title.cfg'):
            local = os.path.join(ra_dir, nome)
            r = subprocess.run(['adb', '-s', f'{TVBOX}:5555', 'push', local, f'/data/local/tmp/{nome}'],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                return False, f'A TV box não recebeu {nome}: {(r.stderr or r.stdout).strip()[-120:]}'
            _sh(f'cp "/data/local/tmp/{nome}" "{destino}/{nome}"; rm -f "/data/local/tmp/{nome}"', 60)
            with open(local, 'rb') as f:
                esperado = hashlib.md5(f.read()).hexdigest()
            remoto = _sh(f'md5sum "{destino}/{nome}"', 60).split()
            if not remoto or remoto[0] != esperado:
                _sh(f'rm -f "{destino}/{nome}"')
                return False, f'A conferência MD5 de {nome} falhou na TV box.'
    except Exception as e:
        return False, f'erro: {e}'
    finally:
        _ra_cache['t'] = 0
    return True, 'SNESticle instalado no pendrive da TV box (OPL → Apps → SNESticle (SNES)).'


def _trabalhador():
    while True:
        _acordar.wait()
        with _trava:
            arq = _fila.pop(0) if _fila else None
            if not arq:
                _acordar.clear()
                continue
        try:
            _copiar(arq)
        except Exception as e:
            _estado[arq].update(fase='erro', msg=str(e))
        _estado[arq]['t'] = time.time()
        _ganchos['atualizou']()


# ---------------- desinstalar ----------------
def desinstalar(arq):
    arq = os.path.basename(arq)
    origem = os.path.join(ORIGEM, arq)
    no_pen, _, _, _ = pendrive()
    if arq not in no_pen:
        return False, 'Não está instalado.'
    if not os.path.isfile(origem) or os.path.getsize(origem) != no_pen[arq]:
        return False, 'Este jogo só existe no pendrive: não apago para não perder.'
    jid, _ = id_nome(arq)
    if jid and _ganchos['jogando']() == jid:
        return False, 'O jogo está aberto no PS2 agora.'
    _sh(f'rm -f "{PEN}/DVD/{arq}"')
    if arq in pendrive()[0]:
        return False, 'Não consegui apagar.'
    _estado.pop(arq, None)
    _ganchos['atualizou']()
    return True, 'Desinstalado: o jogo continua no HD 01TERA.'


def iniciar(capa, atualizou, jogando):
    _ganchos.update(capa=capa, atualizou=atualizou, jogando=jogando)
    threading.Thread(target=_trabalhador, daemon=True).start()
