#!/usr/bin/env python3
"""Trilhas de fundo da Loja (pedido do usuário 24/10/2026: "sons curtos de trilha sonora de games"). Compostas e
sintetizadas aqui, no estilo dos consoles 8-bit (pulso, triângulo e ruído), para não usar música com direitos
autorais: vão no pacote do PS2 Henbox para qualquer um. Cada faixa é um loop de ~30 s que emenda sem corte.
Saída: ../trilhas/<id>.raw (PCM 16 bits mono 22050 Hz, o som do navegador.elf) + ../trilhas/trilhas.json
"""
import json, os, random

import numpy as np

HZ = 22050
SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ps2', 'trilhas')

MAIOR, MENOR = [0, 2, 4, 5, 7, 9, 11], [0, 2, 3, 5, 7, 8, 10]
FAIXAS = [   # id, título, bpm, tônica (MIDI), escala, acordes (graus), semente, clima
    ('aventura', 'Aventura na Floresta', 132, 60, MAIOR, [0, 5, 3, 4], 7, 'alegre'),
    ('corrida', 'Corrida Turbo', 168, 62, MENOR, [0, 5, 6, 4], 11, 'rapido'),
    ('chefao', 'Chefão Final', 150, 57, MENOR, [0, 0, 5, 4], 23, 'tenso'),
    ('gelo', 'Fase do Gelo', 104, 64, MAIOR, [0, 3, 5, 4], 31, 'calmo'),
    ('menu', 'Menu Principal', 116, 65, MAIOR, [0, 4, 5, 3], 42, 'calmo'),
    ('castelo', 'Castelo Assombrado', 96, 55, MENOR, [0, 6, 5, 4], 57, 'tenso'),
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def pulso(f, n, larg=0.5):
    t = np.arange(n) * f / HZ
    return np.where((t % 1.0) < larg, 1.0, -1.0)


def triangulo(f, n):
    t = np.arange(n) * f / HZ
    return 4 * np.abs((t % 1.0) - 0.5) - 1


def envelope(n, ataque=0.005, queda=0.6):
    e = np.ones(n)
    a = max(1, int(ataque * HZ))
    e[:a] = np.linspace(0, 1, a)
    e *= np.exp(-np.arange(n) / HZ / max(queda, 1e-3))
    fim = min(n, int(0.01 * HZ))
    e[-fim:] *= np.linspace(1, 0, fim)
    return e


def nota_escala(tonica, escala, grau, oitava=0):
    o, g = divmod(grau, len(escala))
    return tonica + escala[g] + 12 * (o + oitava)


def compor(bpm, tonica, escala, acordes, semente, clima):
    r = random.Random(semente)
    passo = 60 / bpm / 4                       # semicolcheia
    compassos = 16                             # 4 voltas da progressão
    while compassos * 16 * passo < 26:         # ~30 s de loop
        compassos += 4
    n_passos = compassos * 16
    total = int(n_passos * passo * HZ)
    mix = np.zeros(total + HZ)
    ps = int(passo * HZ)

    def por(inicio, sinal, vol):
        i = int(inicio * ps)
        mix[i:i + len(sinal)] += sinal * vol

    # melodia: frases de 2 compassos, repetidas com variação (o ouvido reconhece "tema")
    frases = []
    for _ in range(2):
        f, grau = [], r.choice([0, 2, 4])
        for k in range(32):
            if r.random() < (0.55 if clima != 'rapido' else 0.7) or k % 8 == 0:
                grau = max(-2, min(9, grau + r.choice([-2, -1, -1, 1, 1, 2, 0, 3, -3])))
                f.append((k, grau, r.choice([1, 2, 2, 3, 4]) if clima != 'rapido' else r.choice([1, 1, 2])))
        frases.append(f)
    larg_melodia = {'alegre': 0.25, 'rapido': 0.125, 'tenso': 0.5, 'calmo': 0.25}[clima]
    for c in range(0, compassos, 2):
        frase = frases[(c // 2) % 2] if (c // 4) % 4 != 3 else frases[0]
        for k, grau, dur in frase:
            m = nota_escala(tonica, escala, grau, 1)
            n = int(dur * ps * 0.95)
            por(c * 16 + k, pulso(hz(m), n, larg_melodia) * envelope(n, queda=0.35 if clima != 'calmo' else 0.8), 0.13)
    # acordes em arpejo (pulso fino) e baixo (triângulo)
    for c in range(compassos):
        raiz = acordes[c % len(acordes)]
        tri = [nota_escala(tonica, escala, raiz + d) for d in (0, 2, 4)]
        for k in range(16):
            if clima == 'calmo' and k % 2:
                continue
            m = tri[k % 3] + (12 if k % 6 >= 3 else 0)
            n = int(ps * (1.9 if clima == 'calmo' else 0.9))
            por(c * 16 + k, pulso(hz(m), n, 0.125) * envelope(n, queda=0.12), 0.05)
        baixo = nota_escala(tonica, escala, raiz, -2)
        padrao = [0, 4, 8, 12] if clima in ('calmo', 'tenso') else [0, 2, 4, 6, 8, 10, 12, 14]
        for k in padrao:
            m = baixo + (12 if clima == 'rapido' and k % 4 == 2 else 0)
            n = int(ps * (3.5 if len(padrao) == 4 else 1.8))
            por(c * 16 + k, triangulo(hz(m), n) * envelope(n, queda=0.5), 0.22)
    # bateria: bumbo (triângulo descendo), caixa e chimbal (ruído)
    ruido = np.random.default_rng(semente).uniform(-1, 1, int(0.2 * HZ))
    for p in range(n_passos):
        k = p % 16
        if k in (0, 8) or (clima == 'rapido' and k in (4, 12)) or (clima == 'alegre' and k == 10):
            n = int(0.12 * HZ)
            f = np.linspace(150, 45, n)
            bumbo = np.sin(2 * np.pi * np.cumsum(f) / HZ) * envelope(n, 0.001, 0.05)
            por(p, bumbo, 0.35)
        if k in (4, 12) and clima != 'calmo':
            n = int(0.1 * HZ)
            por(p, ruido[:n] * envelope(n, 0.001, 0.04), 0.16)
        if k % 2 == 0 or clima == 'rapido':
            n = int(0.03 * HZ)
            por(p, ruido[-n:] * envelope(n, 0.001, 0.008), 0.05 if clima != 'calmo' else 0.025)
    # loop: o que passou do fim volta para o começo (as notas longas emendam sem corte)
    mix[:HZ] += mix[total:total + HZ]
    mix = mix[:total]
    mix /= max(1e-6, np.abs(mix).max())
    return (mix * 0.7 * 32767).astype('<i2').tobytes(), total / HZ


if __name__ == '__main__':
    os.makedirs(SAIDA, exist_ok=True)
    lista = []
    for fid, titulo, bpm, tonica, escala, acordes, semente, clima in FAIXAS:
        d, seg = compor(bpm, tonica, escala, acordes, semente, clima)
        with open(os.path.join(SAIDA, fid + '.raw'), 'wb') as f:
            f.write(d)
        lista.append({'id': fid, 'titulo': titulo, 'segundos': round(seg, 1), 'credito': 'PS2 Henbox (original, livre)'})
        print(f'{fid}: {seg:.1f} s, {len(d) >> 10} KB')
    with open(os.path.join(SAIDA, 'trilhas.json'), 'w', encoding='utf-8') as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
