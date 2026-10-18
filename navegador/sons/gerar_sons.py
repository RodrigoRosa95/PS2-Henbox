#!/usr/bin/env python3
"""Gera os sons do navegador do PS2 (pedido do usuário 16/10/2026: "som na loja"), sintetizados aqui para não usar
música com direitos autorais. Saída PCM 16 bits mono 22050 Hz em ../ps2/ (lida pelo PS2 via host:):
  clique.raw  — "tic" curto ao apertar X / clicar
  musica.raw  — fundo ambiente da loja, 4 acordes em loop de ~25 s (emenda sem estalo)
"""
import math, os, struct

HZ = 22050
SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ps2')


def gravar(nome, amostras):
    with open(os.path.join(SAIDA, nome), 'wb') as f:
        f.write(b''.join(struct.pack('<h', max(-32767, min(32767, int(v * 32767)))) for v in amostras))


def nota(n):   # MIDI → Hz
    return 440 * 2 ** ((n - 69) / 12)


# clique: dois senos agudos com queda rápida
clique = [(0.5 * math.sin(2 * math.pi * 1900 * t / HZ) + 0.25 * math.sin(2 * math.pi * 3800 * t / HZ))
          * math.exp(-t / HZ * 90) for t in range(int(HZ * 0.06))]
gravar('clique.raw', clique)

# música: Cmaj7 – Am7 – Fmaj7 – G6, 6,25 s cada; pad (senos com ataque lento) + sininho em arpejo
ACORDES = [[48, 60, 64, 67, 71], [45, 57, 60, 64, 67], [41, 57, 60, 64, 69], [43, 55, 59, 62, 64]]
DUR = 6.25
total = int(HZ * DUR * len(ACORDES))
musica = [0.0] * total
for i, ac in enumerate(ACORDES):
    ini = int(HZ * DUR * i)
    freqs = [nota(n) for n in ac]
    for t in range(int(HZ * DUR)):
        s = t / HZ
        env = min(1, s / 1.2) * min(1, (DUR - s) / 1.2)    # entra e sai devagar: emenda lisa
        v = sum(math.sin(2 * math.pi * f * s + k) * (0.5 if k == 0 else 0.22) for k, f in enumerate(freqs))
        musica[ini + t] += 0.18 * env * v
    for j in range(8):   # arpejo de sininho, uma nota a cada ~0,78 s
        f = nota(ac[1 + j % 4] + 12)
        p0 = ini + int(HZ * DUR / 8 * j)
        for t in range(int(HZ * 0.7)):
            if p0 + t < total:
                s = t / HZ
                musica[p0 + t] += 0.12 * math.exp(-s * 5) * (math.sin(2 * math.pi * f * s) + 0.3 * math.sin(4 * math.pi * f * s))
pico = max(abs(v) for v in musica)
gravar('musica.raw', [v / pico * 0.6 for v in musica])
print('ok', len(clique), 'amostras de clique,', round(total / HZ, 1), 's de música')
