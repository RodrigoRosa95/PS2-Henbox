"""Gerador de chaves de acesso ao servidor do jogo em nuvem (pedido do usuário 22/10/2026), usado pelo painel ps2-web.

As chaves ficam em navegador/videos_https.chaves.json (só o dono lê); o videos_https.py (ps2-videos) relê o arquivo
quando ele muda, então criar/revogar vale na hora. Cada chave dá à TV box de outra pessoa o mesmo acesso da chave
principal (loja, vídeos, ROMs e ISOs) até ser revogada ou vencer. Uso (última vez, MB servidos): videos_https.uso.json.
"""
import json, os, re, secrets, threading, time

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'navegador')
ARQ = os.path.join(PASTA, 'videos_https.chaves.json')
ARQ_USO = os.path.join(PASTA, 'videos_https.uso.json')
SERVIDOR = 'https://ps2videos.rodrigoflix.com'
DOWNLOADS = 'https://github.com/RodrigoRosa95/ps2GamesCLoudinOPl/releases/latest'
_trava = threading.Lock()


def _ler():
    try:
        return json.load(open(ARQ)).get('chaves', [])
    except (OSError, ValueError):
        return []


def _gravar(lista):
    tmp = ARQ + '.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        json.dump({'chaves': lista}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)


def listar():
    try:
        uso = json.load(open(ARQ_USO))
    except (OSError, ValueError):
        uso = {}
    agora = time.time()
    saida = []
    for c in _ler():
        u = uso.get(c['id'], {})
        estado = 'revogada' if not c.get('ativa', True) else 'vencida' if c.get('expira') and c['expira'] <= agora else 'ativa'
        saida.append(dict(c, estado=estado, ultimo_uso=u.get('ultimo', 0), mb=round(u.get('bytes', 0) / 1048576)))
    return {'chaves': saida, 'servidor': SERVIDOR, 'downloads': DOWNLOADS}


def criar(nome, dias=0):
    nome = re.sub(r'\s+', ' ', str(nome or '')).strip()[:40]
    if not nome:
        return False, 'Dê um nome para saber de quem é a chave.'
    try:
        dias = max(0, min(int(dias or 0), 3650))
    except (TypeError, ValueError):
        dias = 0
    with _trava:
        lista = _ler()
        c = {'id': secrets.token_hex(4), 'nome': nome, 'chave': secrets.token_urlsafe(32),
             'criada': int(time.time()), 'expira': int(time.time() + dias * 86400) if dias else 0, 'ativa': True}
        lista.append(c)
        _gravar(lista)
    return True, c


def mudar(cid, acao):
    with _trava:
        lista = _ler()
        alvo = next((c for c in lista if c['id'] == cid), None)
        if not alvo:
            return False, 'Chave não encontrada.'
        if acao == 'revogar':
            alvo['ativa'] = False
        elif acao == 'reativar':
            alvo['ativa'] = True
        elif acao == 'apagar':
            lista.remove(alvo)
        else:
            return False, 'Ação inválida.'
        _gravar(lista)
    return True, 'ok'
