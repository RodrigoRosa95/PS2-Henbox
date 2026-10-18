"""PS2 no painel casa-nossa do Home Assistant (pedido do usuário 16/10/2026).

- Sensores enviados pela API REST do HA a cada 20 s (somem se o HA reiniciar, até o próximo envio):
    sensor.ps2_status   Desligado | Ligado | PS2Link | wLaunchELF (FTP) | Jogando
    sensor.ps2_jogo     jogo atual ou último, com a capa (entity_picture servida por esta página)
    sensor.ps2_tempo_hoje / sensor.ps2_tempo_semana   minutos jogados (estatisticas.py)
    sensor.ps2_mensagem resultado do último botão
    sensor.ps2_temperatura  °C da última leitura (temperatura.py; só enquanto um app nosso roda no PS2)
- Ajudantes criados pelo websocket (o HA não tem YAML editável aqui nem rest_command para esta página):
    input_select.ps2_jogo (lista de jogos), input_button.ps2_jogar, input_button.ps2_reiniciar,
    input_button.ps2_desligar. Este módulo ouve os botões e chama jogar()/sistema() do servidor.py.
"""
import json, os, socket, threading, time, urllib.request

import websocket

import estatisticas
import temperatura
from voz import _env, log

PAGINA = 'http://192.168.4.135:8770'
PS2 = '192.168.4.230'
BOTOES = {'input_button.ps2_jogar': 'jogar', 'input_button.ps2_reiniciar': 'reiniciar',
          'input_button.ps2_desligar': 'desligar'}
_estado = {'msg': 'Pronto.'}


def _post(env, caminho, dados):
    req = urllib.request.Request(env['HA_URL'] + caminho, method='POST', data=json.dumps(dados).encode(),
                                 headers={'Authorization': 'Bearer ' + env['HA_TOKEN'],
                                          'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=15).read()


def _porta(porta):
    try:
        socket.create_connection((PS2, porta), timeout=1.5).close()
        return True
    except OSError:
        return False


def _status(trava_ps2):
    r = estatisticas.resumo([])
    if r['atual']:
        return 'Jogando', r
    try:
        online = json.load(open(os.path.join(estatisticas.PASTA, 'status.json')))['ps2']['online']
    except (OSError, ValueError, KeyError):
        online = False
    if os.system(f'ping -c1 -W1 {PS2} >/dev/null 2>&1') == 0:
        if _porta(21):
            return 'wLaunchELF (FTP)', r
        try:   # navegador do PS2 aberto?
            with socket.create_connection((os.environ.get('PS2_NAV_IP', '127.0.0.1'), 8772), timeout=2) as c:
                c.sendall(b'status\n')
                if c.recv(16).startswith(b'aberto'):
                    return 'Navegador', r
        except OSError:
            pass
        return 'PS2Link', r   # o PS2Link não tem porta TCP; ligado, sem FTP, sem jogo e sem navegador = PS2Link
    return ('Ligado' if online else 'Desligado'), r


def _enviar_sensores(env, trava_ps2):
    st, r = _status(trava_ps2)
    try:
        ps2 = json.load(open(os.path.join(estatisticas.PASTA, 'status.json')))['ps2']
    except (OSError, ValueError, KeyError):
        ps2 = {}
    atual = r['atual'] or {}
    nome = atual.get('nome') or ps2.get('jogo') or 'Nenhum'
    jid = atual.get('id') or ps2.get('jogo_id') or ''
    capa = f'{PAGINA}/capas/{jid}.jpg' if jid and os.path.exists(
        os.path.join(estatisticas.PASTA, 'capas', jid + '.jpg')) else None
    icone = {'Desligado': 'mdi:sony-playstation', 'Jogando': 'mdi:gamepad-variant'}.get(st, 'mdi:sony-playstation')
    sensores = {
        'sensor.ps2_status': (st, {'friendly_name': 'PS2', 'icon': icone, 'pagina': PAGINA}),
        'sensor.ps2_jogo': (nome[:250], {'friendly_name': 'PS2 jogo' if r['atual'] else 'PS2 último jogo',
                                         'icon': 'mdi:disc', 'entity_picture': capa, 'id': jid,
                                         'origem': atual.get('origem', ''),
                                         'jogando_ha_min': round(atual.get('seg', 0) / 60) if atual else 0}),
        'sensor.ps2_tempo_hoje': (round(r['hoje_s'] / 60), {'friendly_name': 'PS2 jogado hoje',
                                                          'unit_of_measurement': 'min', 'icon': 'mdi:timer-outline'}),
        'sensor.ps2_tempo_semana': (round(r['semana_s'] / 60), {'friendly_name': 'PS2 jogado na semana',
                                                              'unit_of_measurement': 'min', 'icon': 'mdi:calendar-week'}),
        'sensor.ps2_mensagem': (_estado['msg'][:250], {'friendly_name': 'PS2 último comando', 'icon': 'mdi:message-text'}),
    }
    t = temperatura.atual()
    if t['c'] is not None:
        sensores['sensor.ps2_temperatura'] = (t['c'], {
            'friendly_name': 'PS2 temperatura', 'unit_of_measurement': '°C', 'device_class': 'temperature',
            'state_class': 'measurement', 'icon': 'mdi:thermometer', 'lida_ha_min': round(t['idade_s'] / 60),
            'origem': t['origem'], 'max_hoje': t['max_hoje']})
    for e, (v, attrs) in sensores.items():
        _post(env, '/api/states/' + e, {'state': v, 'attributes': {k: a for k, a in attrs.items() if a is not None}})


class _WS:
    def __init__(self, env):
        self.ws = websocket.create_connection(env['HA_URL'].replace('http', 'ws', 1) + '/api/websocket', timeout=30)
        self.ws.recv()
        self.ws.send(json.dumps({'type': 'auth', 'access_token': env['HA_TOKEN']}))
        if json.loads(self.ws.recv()).get('type') != 'auth_ok':
            raise RuntimeError('token do HA recusado')
        self.n = 0

    def cmd(self, **k):
        self.n += 1
        k['id'] = self.n
        self.ws.send(json.dumps(k))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == self.n:
                if not r.get('success'):
                    raise RuntimeError(f"{k['type']}: {r.get('error')}")
                return r.get('result')


def _ajudantes(env, nomes):
    """Cria (uma vez) os ajudantes e mantém a lista de jogos atualizada."""
    ws = _WS(env)
    botoes = {b['name']: b for b in ws.cmd(type='input_button/list')}
    for nome, icone in (('PS2 jogar', 'mdi:play'), ('PS2 reiniciar', 'mdi:restart'), ('PS2 desligar', 'mdi:power')):
        if nome not in botoes:
            ws.cmd(type='input_button/create', name=nome, icon=icone)
    sel = {s['name']: s for s in ws.cmd(type='input_select/list')}
    if nomes:
        if 'PS2 jogo' not in sel:
            ws.cmd(type='input_select/create', name='PS2 jogo', options=nomes, icon='mdi:disc')
        elif sel['PS2 jogo']['options'] != nomes:
            ws.cmd(type='input_select/update', input_select_id=sel['PS2 jogo']['id'], name='PS2 jogo',
                   options=nomes, icon='mdi:disc')
    ws.ws.close()


def _apertou(env, acao, jogos, jogar, sistema):
    if acao == 'jogar':
        try:
            req = urllib.request.Request(env['HA_URL'] + '/api/states/input_select.ps2_jogo',
                                         headers={'Authorization': 'Bearer ' + env['HA_TOKEN']})
            nome = json.load(urllib.request.urlopen(req, timeout=10))['state']
        except Exception:
            nome = ''
        jogo = next((j for j in jogos() if j['nome'] == nome), None)
        if not jogo:
            _estado['msg'] = f'Jogo "{nome}" não encontrado.'
        else:
            _estado['msg'] = f"Abrindo {jogo['nome']}…"
            _enviar_sensores(env, threading.Lock())
            ok, msg, _ = jogar(jogo['id'])
            _estado['msg'] = msg
    else:
        _estado['msg'] = 'Reiniciando…' if acao == 'reiniciar' else 'Desligando…'
        _enviar_sensores(env, threading.Lock())
        ok, msg = sistema(acao)
        _estado['msg'] = msg
    log('painel HA', acao, '→', _estado['msg'])


def _laco_botoes(env, jogos, jogar, sistema):
    vistos = {}
    while True:
        try:
            ws = _WS(env)
            ws.ws.send(json.dumps({'id': 99, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
            ws.ws.settimeout(None)
            while True:
                d = (json.loads(ws.ws.recv()).get('event') or {}).get('data') or {}
                e = d.get('entity_id', '')
                novo = (d.get('new_state') or {}).get('state')
                antigo = (d.get('old_state') or {}).get('state')
                if e in BOTOES and novo not in (None, 'unknown', 'unavailable') and antigo and novo != vistos.get(e):
                    vistos[e] = novo
                    threading.Thread(target=_apertou, args=(env, BOTOES[e], jogos, jogar, sistema), daemon=True).start()
        except Exception as ex:
            log('painel HA: conexão caiu:', ex)
            time.sleep(30)


def _laco_sensores(env, jogos, trava_ps2):
    ultima_lista = None
    while True:
        try:
            nomes = [j['nome'] for j in jogos()]
            if nomes and nomes != ultima_lista:
                _ajudantes(env, nomes)
                ultima_lista = nomes
            _enviar_sensores(env, trava_ps2)
        except Exception as ex:
            log('painel HA: sensores:', ex)
        time.sleep(20)


def iniciar(jogos, jogar, sistema, trava_ps2):
    env = _env()
    threading.Thread(target=_laco_sensores, args=(env, jogos, trava_ps2), daemon=True).start()
    threading.Thread(target=_laco_botoes, args=(env, jogos, jogar, sistema), daemon=True).start()
