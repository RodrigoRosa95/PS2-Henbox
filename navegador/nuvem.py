"""Memory card na nuvem e atualização do navegador.elf, do lado da TV box (pedido do usuário 22/10/2026).

Memory card: o Neutrino do "Jogar pela rede" recebe -mc0=udpfs:MC/mc0.bin e lê/grava o cartão no udpfs_nuvem.py
desta box, que guarda o arquivo em ~/ps2nav/mc/ (o pendrive da box é só leitura pelo Termux). O servidor
(videos_https.py, /mc/<nome>) guarda um cartão por chave de acesso, com as versões anteriores:
  - mc_baixar(): antes de abrir o jogo, traz a versão do servidor se for mais nova (se aqui houver gravação ainda não
    enviada, envia primeiro — a gravação local ganha);
  - mc_marcar(): o udpfs_nuvem.py avisa a cada gravação do PS2; mc_vigiar() envia o cartão 15 s depois da última.
Cartão novo: 8 MB apagados (0xFF); o próprio jogo formata na primeira vez. "mc_nuvem": false no remoto.json desliga.

Atualização: atualizar_navegador() compara o ps2/navegador.elf desta box com o publicado no servidor
(/atualizacao/versao.json) e baixa o novo, conferindo o SHA-256. O navegador_servidor.py depois regrava o do pendrive.
"""
import gzip, hashlib, http.client, json, os, threading, time, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
REMOTO = os.path.expanduser('~/ps2nav/remoto.json')
MC_DIR = os.path.expanduser('~/ps2nav/mc')
MC_NOME = 'mc0.bin'
MC_TAM = 8 << 20
MC_ESPERA = 15   # segundos sem gravação antes de enviar (o jogo terminou de salvar)
_url_boa = ['']
_trava_mc = threading.Lock()


def log(*a):
    print(time.strftime('%H:%M:%S'), 'nuvem:', *a, flush=True)


def cfg():
    try:
        return json.load(open(REMOTO))
    except (OSError, ValueError):
        return {}


def pedir(metodo, caminho, corpo=None, cabecalhos=None, timeout=60):
    """(status, cabeçalhos, dados) do primeiro endereço do remoto.json que responder (o último bom primeiro)."""
    c = cfg()
    if not c.get('chave'):
        raise OSError('sem chave no remoto.json')
    erro = None
    for url in sorted(c.get('urls', []), key=lambda u: u != _url_boa[0]):
        u = urllib.parse.urlparse(url)
        Cls = http.client.HTTPSConnection if u.scheme == 'https' else http.client.HTTPConnection
        con = Cls(u.netloc, timeout=3 if u.scheme == 'http' and url != _url_boa[0] else timeout)
        try:
            con.request(metodo, caminho, body=corpo, headers=dict(cabecalhos or {}, **{'X-Chave': c['chave']}))
            r = con.getresponse()
            dados = r.read()
            _url_boa[0] = url
            return r.status, {k.lower(): v for k, v in r.getheaders()}, dados
        except Exception as e:
            erro = e
        finally:
            con.close()
    raise OSError(f'servidor fora do alcance ({erro})')


# ---------------------------------------------------------------- memory card

def mc_ativo():
    c = cfg()
    return bool(c.get('urls') and c.get('chave')) and c.get('mc_nuvem', True) is not False


def _meta():
    try:
        return json.load(open(os.path.join(MC_DIR, MC_NOME + '.json')))
    except (OSError, ValueError):
        return {'versao': '', 'sujo': False, 't': 0}


def _gravar_meta(m):
    tmp = os.path.join(MC_DIR, MC_NOME + '.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(m, f)
    os.replace(tmp, os.path.join(MC_DIR, MC_NOME + '.json'))


def _gravar_cartao(dados):
    tmp = os.path.join(MC_DIR, MC_NOME + '.tmp')
    with open(tmp, 'wb') as f:
        f.write(dados)
    os.replace(tmp, os.path.join(MC_DIR, MC_NOME))


def mc_enviar():
    """Manda o cartão ao servidor (compactado). True se o servidor ficou com esta versão."""
    with _trava_mc:
        m = _meta()
        arq = os.path.join(MC_DIR, MC_NOME)
        if not os.path.exists(arq):
            return False
        m_antes = m['t']
        dados = open(arq, 'rb').read()
        try:
            st, cab, resp = pedir('PUT', '/mc/' + MC_NOME, gzip.compress(dados, 6),
                                  {'Content-Encoding': 'gzip', 'Content-Type': 'application/octet-stream',
                                   'X-Base': m.get('versao', '')})
        except OSError as e:
            log('memory card: envio falhou,', e)
            return False
        if st != 200:
            log('memory card: envio recusado,', st, resp[:80])
            return False
        m = _meta()
        m['versao'] = cab.get('x-versao', '')
        if m['t'] == m_antes:   # nada gravado enquanto enviava
            m['sujo'] = False
        _gravar_meta(m)
        log(f'memory card enviado ({len(dados) >> 10} KB, versão {m["versao"][:8]})')
        return True


def mc_baixar():
    """Antes do jogo: deixa ~/ps2nav/mc/mc0.bin com a versão mais nova. Sem servidor, segue com a local."""
    os.makedirs(MC_DIR, exist_ok=True)
    arq = os.path.join(MC_DIR, MC_NOME)
    m = _meta()
    if m.get('sujo'):
        mc_enviar()
        m = _meta()
    try:
        st, cab, dados = pedir('GET', '/mc/' + MC_NOME, cabecalhos={'X-Versao-Local': m.get('versao', ''),
                                                               'Accept-Encoding': 'gzip'})
    except OSError as e:
        log('memory card: servidor fora,', e, '— usando o da box')
        st = None
    with _trava_mc:
        if st == 200 and cab.get('x-versao') != m.get('versao'):
            dados = gzip.decompress(dados) if cab.get('content-encoding') == 'gzip' else dados
            if hashlib.sha256(dados).hexdigest()[:16] == cab.get('x-versao', '')[:16]:
                _gravar_cartao(dados)
                m.update(versao=cab['x-versao'], sujo=False)
                _gravar_meta(m)
                log(f'memory card baixado do servidor (versão {m["versao"][:8]})')
            else:
                log('memory card: cópia do servidor veio estragada, mantendo a da box')
        elif st == 304 or (st == 200 and cab.get('x-versao') == m.get('versao')):
            pass
        if not os.path.exists(arq):
            _gravar_cartao(b'\xff' * MC_TAM)
            m.update(versao='', sujo=False, t=0)
            _gravar_meta(m)
            log('memory card novo criado (o jogo formata na primeira vez)')
    return arq


def mc_marcar():
    """Chamado pelo udpfs_nuvem.py a cada gravação do PS2 no cartão."""
    with _trava_mc:
        m = _meta()
        m.update(sujo=True, t=time.time())
        _gravar_meta(m)


def mc_vigiar():
    """Thread do udpfs_nuvem.py: envia o cartão MC_ESPERA s depois da última gravação."""
    while True:
        time.sleep(5)
        try:
            m = _meta()
            if m.get('sujo') and time.time() - m.get('t', 0) >= MC_ESPERA and mc_ativo():
                if not mc_enviar():
                    time.sleep(60)   # servidor fora: tenta de novo daqui a pouco (a gravação continua na box)
        except Exception as e:
            log('memory card:', e)


# ---------------------------------------------------------------- atualização do navegador.elf

def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def atualizar_navegador(pasta_ps2):
    """Baixa o navegador.elf publicado no servidor se for diferente do desta box. True se trocou."""
    try:
        st, _, dados = pedir('GET', '/atualizacao/versao.json', timeout=20)
        if st != 200:
            return False
        pub = json.loads(dados).get('navegador.elf')
    except (OSError, ValueError) as e:
        log('atualização: sem resposta,', e)
        return False
    local = os.path.join(pasta_ps2, 'navegador.elf')
    if not pub or (os.path.exists(local) and sha256_arquivo(local) == pub['sha256']):
        return False
    try:
        st, _, dados = pedir('GET', '/atualizacao/navegador.elf', timeout=120)
    except OSError as e:
        log('atualização: download falhou,', e)
        return False
    if st != 200 or hashlib.sha256(dados).hexdigest() != pub['sha256']:
        log('atualização: arquivo recebido não confere, mantendo o atual')
        return False
    if os.path.exists(local):
        os.replace(local, local + '.anterior')
    with open(local + '.tmp', 'wb') as f:
        f.write(dados)
    os.chmod(local + '.tmp', 0o700)
    os.replace(local + '.tmp', local)
    log(f'navegador.elf atualizado ({pub["sha256"][:8]}, {len(dados) >> 10} KB)')
    return True
