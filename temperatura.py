"""Temperatura do PS2 (pedido do usuário 17/10/2026): sensor ligado ao Mechacon, lido pelo comando S 0x03/0xEF
(o mesmo do PS2Ident). Só existe nos modelos com Mechacon 5.04+ (slim 7xxxx/9xxxx; o SCPH-90001 tem).

O PS2 só lê enquanto um app nosso está aberto (não dá para ler durante um jogo no OPL nem parado no PS2Link):
  - navegador.elf grava host:temperatura.txt ("41.5") a cada 10 s → navegador/ps2/temperatura.txt
  - loja nativa (AthenaEnv) manda POST /api/ps2/temperatura {"c": 41.5, "origem": "loja-nativa"}
GET /api/ps2/temperatura devolve a última leitura, a idade dela e a máxima/mínima de hoje (temperatura.json).
"""
import json, os, threading, time

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'temperatura.json')
NAVEGADOR = os.path.join(PASTA, 'navegador', 'ps2', 'temperatura.txt')
_trava = threading.Lock()


def _ler():
    try:
        return json.load(open(ARQ))
    except (OSError, ValueError):
        return {'leituras': []}


def registrar(c, origem, quando=None):
    """Guarda uma leitura (°C). Ignora valores fora do possível (sensor ausente devolve lixo)."""
    try:
        c = round(float(c), 1)
    except (TypeError, ValueError):
        return False
    if not 5 <= c <= 110:
        return False
    quando = int(quando or time.time())
    with _trava:
        d = _ler()
        ls = d['leituras']
        if ls and ls[-1][0] >= quando:
            return True
        ls.append([quando, c, origem])
        d['leituras'] = [l for l in ls if l[0] > quando - 7 * 86400][-3000:]
        tmp = ARQ + '.tmp'
        json.dump(d, open(tmp, 'w'))
        os.replace(tmp, ARQ)
    return True


def _do_navegador():
    try:
        quando = os.path.getmtime(NAVEGADOR)
        registrar(open(NAVEGADOR).read().strip(), 'navegador', quando)
    except OSError:
        pass


def atual():
    _do_navegador()
    ls = _ler()['leituras']
    if not ls:
        return {'c': None}
    agora = time.time()
    inicio_dia = time.mktime(time.localtime(agora)[:3] + (0, 0, 0, 0, 0, -1))
    hoje = [l[1] for l in ls if l[0] >= inicio_dia]
    quando, c, origem = ls[-1]
    return {'c': c, 'quando': quando, 'idade_s': int(agora - quando), 'origem': origem,
            'max_hoje': max(hoje) if hoje else None, 'min_hoje': min(hoje) if hoje else None,
            'recentes': [[l[0], l[1]] for l in ls if l[0] > agora - 3 * 3600][-120:]}
