"""Estatísticas de jogo do PS2 (pedido do usuário 16/10/2026): tempo por jogo, hoje/semana/total e sessões.

A cada 15 s descobre o que está rodando:
  - OPL pelo Samba da TV box: status.json do monitor-ps2-tvbox.sh (ps2.jogo_aberto / jogo_id);
  - caminho 2 (Neutrino): neutrino_atual.json gravado pelo ps2-jogar.sh. O Neutrino não usa o Samba, então a
    sessão vale enquanto o servidor udpfs (TV box ou notebook) continua lendo o ISO ou o PS2 responde ao ping;
    15 min sem nenhum dos dois encerram a sessão no último sinal de vida.
Grava tudo em estatisticas.json (nesta pasta).
"""
import json, os, re, subprocess, threading, time

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'estatisticas.json')
STATUS = os.path.join(PASTA, 'status.json')
NEUTRINO = os.path.join(PASTA, 'neutrino_atual.json')
PS2 = '192.168.4.230'
ADB = ['adb', '-s', '192.168.4.121:5555', 'shell']
SILENCIO = 15 * 60
_trava = threading.Lock()
_dados = {'jogos': {}, 'sessoes': [], 'atual': None}
_leituras = {'valor': None, 'visto': 0}   # bytes lidos pelo servidor udpfs e quando mudaram


def _carregar():
    try:
        _dados.update(json.load(open(ARQ)))
    except (OSError, ValueError):
        pass


def _salvar():
    tmp = ARQ + '.tmp'
    json.dump(_dados, open(tmp, 'w'), ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)


def _id_nome(arquivo):
    base = re.sub(r'\.iso$', '', arquivo, flags=re.I)
    m = re.match(r'^([A-Z]{4}_\d{3}\.\d{2})\.(.*)$', base)
    return (m.group(1), m.group(2)) if m else (base, base)


def _bytes_lidos_udpfs():
    """rchar do processo udpfs_server (notebook ou TV box); None se nenhum estiver rodando."""
    total = None
    try:
        for pid in os.listdir('/proc'):
            if pid.isdigit():
                try:
                    cmd = open(f'/proc/{pid}/cmdline', 'rb').read()
                except OSError:
                    continue
                if b'udpfs_server.py' in cmd:
                    io = open(f'/proc/{pid}/io').read()
                    total = (total or 0) + int(re.search(r'rchar: (\d+)', io).group(1))
    except (OSError, AttributeError):
        pass
    try:
        saida = subprocess.run(ADB + ['for p in $(ps -A -o PID,ARGS | grep "[u]dpfs_server" | cut -c1-6); do '
                                      'grep rchar /proc/$p/io; done'],
                               capture_output=True, text=True, timeout=8).stdout
        for n in re.findall(r'rchar: (\d+)', saida):
            total = (total or 0) + int(n)
    except (OSError, subprocess.SubprocessError):
        pass
    return total


def _ping():
    return subprocess.run(['ping', '-c1', '-W1', PS2], capture_output=True).returncode == 0


def _jogo_agora(agora):
    """(id, nome, origem) do que está rodando, ou None."""
    try:
        st = json.load(open(STATUS))
        if time.time() - os.path.getmtime(STATUS) < 60 and st['ps2'].get('jogo_aberto'):
            return st['ps2'].get('jogo_id') or st['ps2']['jogo'], st['ps2']['jogo'], 'OPL'
    except (OSError, ValueError, KeyError):
        pass
    try:
        n = json.load(open(NEUTRINO))
    except (OSError, ValueError):
        return None
    lidos = _bytes_lidos_udpfs()
    if lidos is not None and lidos != _leituras['valor']:
        _leituras.update(valor=lidos, visto=agora)
    vivo = max(_leituras['visto'], n['inicio'])
    if _ping():
        vivo = agora
        _leituras['visto'] = agora
    if agora - vivo > SILENCIO:
        os.replace(NEUTRINO, NEUTRINO + '.fim')
        return None
    jid, nome = _id_nome(n['arquivo'])
    return jid, nome, 'Neutrino'


def _fechar(fim):
    a = _dados['atual']
    if not a:
        return
    seg = max(0, int(fim - a['inicio']))
    _dados['atual'] = None
    if seg < 60:   # abriu e fechou: não conta
        return
    j = _dados['jogos'].setdefault(a['id'], {'nome': a['nome'], 'segundos': 0, 'sessoes': 0, 'ultimo': 0})
    j.update(nome=a['nome'], segundos=j['segundos'] + seg, sessoes=j['sessoes'] + 1, ultimo=int(fim))
    _dados['sessoes'] = (_dados['sessoes'] + [dict(a, fim=int(fim), seg=seg)])[-300:]


def _ciclo():
    agora = time.time()
    with _trava:
        jogo = _jogo_agora(agora)
        a = _dados['atual']
        if a and (not jogo or jogo[0] != a['id']):
            _fechar(a['visto'])
        if jogo:
            if not _dados['atual']:
                _dados['atual'] = {'id': jogo[0], 'nome': jogo[1], 'origem': jogo[2], 'inicio': int(agora)}
            _dados['atual']['visto'] = int(agora)
        _salvar()


def _laco():
    while True:
        try:
            _ciclo()
        except Exception as e:  # o laço não pode morrer
            print('estatisticas:', e, flush=True)
        time.sleep(15)


def iniciar():
    _carregar()
    a = _dados['atual']
    if a and time.time() - a.get('visto', 0) > SILENCIO:   # servidor ficou fora: fecha no último sinal
        _fechar(a['visto'])
    threading.Thread(target=_laco, daemon=True).start()


def resumo(lista_jogos):
    capas = {j['id']: j.get('capa', '') for j in lista_jogos}
    agora = time.time()
    lt = time.localtime(agora)
    hoje = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    semana = hoje - lt.tm_wday * 86400   # desde segunda-feira
    with _trava:
        sessoes = list(_dados['sessoes'])
        a = dict(_dados['atual']) if _dados['atual'] else None
        tot = {k: dict(v) for k, v in _dados['jogos'].items()}
    if a:
        a['seg'] = int(a['visto'] - a['inicio'])
        sessoes_todas = sessoes + [dict(a, fim=a['visto'])]
        t = tot.setdefault(a['id'], {'nome': a['nome'], 'segundos': 0, 'sessoes': 0, 'ultimo': 0})
        t.update(segundos=t['segundos'] + a['seg'], ultimo=a['visto'])
    else:
        sessoes_todas = sessoes

    def soma(desde):   # só a parte de cada sessão depois de "desde"
        return sum(max(0, s['fim'] - max(s['inicio'], desde)) for s in sessoes_todas)
    ranking = sorted(({'id': k, **v, 'capa': capas.get(k) or (f'capas/{k}.jpg' if os.path.exists(
        os.path.join(PASTA, 'capas', k + '.jpg')) else '')} for k, v in tot.items()),
        key=lambda j: -j['segundos'])
    return {'atual': a, 'hoje_s': soma(hoje), 'semana_s': soma(semana),
            'total_s': sum(j['segundos'] for j in ranking), 'jogos': ranking,
            'recentes': [dict(s, capa=capas.get(s['id'], '')) for s in reversed(sessoes_todas[-10:])]}
