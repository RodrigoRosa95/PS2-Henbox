#!/usr/bin/env python3
"""Passo 1: decifra o SEU Option File original (BASE/original/<pasta>/<arquivo>) para BASE/opcao_decifrada.bin e extrai
os nomes dos jogadores (BASE/nomes.txt). Os outros scripts partem desses dois arquivos."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE
from pes14fmt import *

SAVE = 'BESLES-556762014OPT'
orig = open(f'{BASE}/original/{SAVE}/{SAVE}', 'rb').read()
if len(orig) != 1086464:
    sys.exit(f'tamanho inesperado ({len(orig)} bytes): este projeto foi feito para o Option File PAL do PES 2014 (1086464 bytes)')
for ini, tam in BL:
    if chk(orig, ini, tam) != struct.unpack_from('<I', orig, ini - 8)[0]:
        sys.exit(f'o checksum do bloco 0x{ini:x} não bate: este não é um Option File íntegro do PES 2014 PAL')
p = abrir(orig)
assert fechar(p) == orig, 'round-trip não idêntico'
open(f'{BASE}/opcao_decifrada.bin', 'wb').write(p)
open(f'{BASE}/nomes.txt', 'w').write('\n'.join(f'{i}\t{nome_jogador(p, i)}' for i in range(NJOG)))
print('ok: decifrado, checksums conferidos, round-trip idêntico;', NJOG, 'jogadores,', NTIMES, 'times')
