"""Comandos de voz do PS2 pela Echo (pedido do usuário 16/10/2026): "Alexa, abrir GTA", "Alexa, jogar God of War 2 no
PS2", "Alexa, reiniciar o PS2", "Alexa, desligar o PS2".

O HA Cloud está sem assinatura, então a Alexa não chama o HA. Igual à automação "Comandos de voz das cenas sem a
nuvem (Echo Dot)", aqui se lê o evento de voz da integração alexa_devices (event.*_voice_event, com o texto falado em
voice_command) pela API de websocket do HA. O comando chega 7 a 22 s depois da fala; a Alexa responde que não sabe e
em seguida a Echo que ouviu fala o resultado (notify.<echo>_speak). Log em voz.log.
"""
import json, os, re, threading, time, unicodedata, urllib.request

import websocket

PASTA = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(PASTA, 'voz.log')
VERBO = r'(abr\w*|jog\w*|inici\w*|rod\w*|carreg\w*|coloc\w*|bot\w*|liga\w*|ativ\w*)'
PS2 = r'(ps ?2|ps dois|pe esse dois|play ?station ?(2|dois)|play ?(2|dois)|playstation)'
ALIAS = {'gta': 'grand theft auto san andreas', 'gta san andreas': 'grand theft auto san andreas',
         'san andreas': 'grand theft auto san andreas', 'pes': 'pro evolution soccer',
         'cod': 'call of duty', 'nfs': 'need for speed', 'naruto': 'naruto shippuden'}
NUMEROS = {'um': '1', 'i': '1', 'dois': '2', 'ii': '2', 'tres': '3', 'iii': '3', 'quatro': '4', 'cinco': '5'}
IGNORAR = {'o', 'a', 'no', 'na', 'do', 'da', 'de', 'e', 'jogo', 'game', 'pra', 'para', 'mim', 'por', 'favor', 'meu',
           'agora', 'ai', 'alexa', 'ps2', 'video'}


def _env():
    d = {}
    for linha in open(os.path.expanduser('~/.env')):
        if linha.startswith(('HA_URL=', 'HA_TOKEN=')):
            k, v = linha.strip().split('=', 1)
            d[k] = v.strip('"\'')
    return d


def log(*a):
    with open(LOG, 'a') as f:
        print(time.strftime('%d/%m %H:%M:%S'), *a, file=f)


def norm(t):
    t = unicodedata.normalize('NFD', t.lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9 ]+', ' ', t).strip()


def fichas(t):
    return [NUMEROS.get(p, p) for p in norm(t).split() if p not in IGNORAR]


def achar_jogo(pedido, lista):
    """Devolve (jogo, outros): jogo único que contém todas as palavras do pedido, ou None e os candidatos."""
    p = ' '.join(fichas(pedido))
    apelidos = '|'.join(re.escape(k) for k in sorted(ALIAS, key=len, reverse=True))
    p = re.sub(rf'(?<!\S)({apelidos})(?!\S)', lambda m: ALIAS[m.group(1)], p)   # "gta", "pes 2014"...
    q = set(fichas(p))
    if not q:
        return None, []
    cands = [j for j in lista if q <= set(fichas(j['nome']))]
    if len(cands) > 1:   # "god of war 2" casa com "God Of War 2" só; "god of war" casa com os dois
        exatos = [j for j in cands if set(fichas(j['nome'])) == q]
        cands = exatos or cands
    return (cands[0], []) if len(cands) == 1 else (None, cands)


def entender(comando, lista):
    """('jogar', jogo) | ('sistema', 'reiniciar'|'desligar') | ('duvida', texto) | None (não é com o PS2)."""
    c = norm(comando)
    c = re.sub(r'^alexa\s+', '', c)
    fala_ps2 = re.search(rf'(^| ){PS2}( |$)', c) is not None
    if fala_ps2 and re.search(r'(^| )(reinici|reset)\w*', c):
        return 'sistema', 'reiniciar'
    if fala_ps2 and re.search(r'(^| )deslig\w*', c):
        return 'sistema', 'desligar'
    m = re.match(rf'^{VERBO}\s+(.*)$', c)
    if not m:
        return None
    pedido = re.sub(rf'(^| ){PS2}( |$)', ' ', m.group(2))
    jogo, outros = achar_jogo(pedido, lista)
    if jogo:
        return 'jogar', jogo
    if outros:
        return 'duvida', 'Tenho ' + ', '.join(j['nome'] for j in outros[:4]) + '. Diga qual.'
    if fala_ps2:
        return 'duvida', 'Não achei esse jogo no PS2.'
    return None   # "abrir youtube" etc.: é de outra automação


def falar(env, echo, texto):
    alvo = f'notify.{echo}_speak'
    req = urllib.request.Request(env['HA_URL'] + '/api/services/notify/send_message', method='POST',
                                 data=json.dumps({'entity_id': alvo, 'message': texto}).encode(),
                                 headers={'Authorization': 'Bearer ' + env['HA_TOKEN'],
                                          'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        log('erro ao falar', alvo, e)


FALAS_ERRO = {4: 'O servidor de jogos da TV box não subiu.',
              5: 'O PS2 não está no PS2Link. Abra o OPL, aba Apps, PS2Link, e peça de novo.',
              6: 'O PS2 está no wLaunchELF. Abra o PS2Link e peça de novo.'}


def tratar(env, entidade, comando, jogos, jogar, sistema):
    acao = entender(comando, jogos())
    if not acao:
        return
    echo = entidade.removeprefix('event.').removesuffix('_voice_event')
    log(entidade, repr(comando), '→', acao[0], acao[1]['nome'] if acao[0] == 'jogar' else acao[1])
    if acao[0] == 'duvida':
        return falar(env, echo, acao[1])
    if acao[0] == 'sistema':
        ok, msg = sistema(acao[1])
        log('  ', ok, msg)
        return falar(env, echo, msg if not ok else ('PS2 desligado.' if acao[1] == 'desligar' else 'Reiniciando o PS2.'))
    jogo = acao[1]
    ok, msg, codigo = jogar(jogo['id'])
    log('  ', ok, codigo, msg)
    falar(env, echo, f"Abrindo {jogo['nome']} no PS2." if ok else
          FALAS_ERRO.get(codigo, f"Não consegui abrir {jogo['nome']}. {msg}"))


def _laco(jogos, jogar, sistema):
    env = _env()
    vistos = {}
    while True:
        try:
            ws = websocket.create_connection(env['HA_URL'].replace('http', 'ws', 1) + '/api/websocket', timeout=60)
            ws.recv()
            ws.send(json.dumps({'type': 'auth', 'access_token': env['HA_TOKEN']}))
            if json.loads(ws.recv()).get('type') != 'auth_ok':
                raise RuntimeError('token do HA recusado')
            ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
            ws.settimeout(None)
            log('ouvindo a Echo pelo HA')
            while True:
                ev = json.loads(ws.recv())
                d = (ev.get('event') or {}).get('data') or {}
                e = d.get('entity_id', '')
                novo = d.get('new_state') or {}
                if not (e.startswith('event.') and e.endswith('_voice_event')):
                    continue
                if novo.get('state') in (None, 'unknown', 'unavailable') or vistos.get(e) == novo['state']:
                    continue
                vistos[e] = novo['state']
                cmd = (novo.get('attributes') or {}).get('voice_command') or ''
                if cmd:
                    threading.Thread(target=tratar, args=(env, e, cmd, jogos, jogar, sistema), daemon=True).start()
        except Exception as ex:
            log('conexão com o HA caiu:', ex)
            time.sleep(30)


def iniciar(jogos, jogar, sistema):
    threading.Thread(target=_laco, args=(jogos, jogar, sistema), daemon=True).start()
