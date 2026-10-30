#!/usr/bin/env python3
"""Hash RetroAchievements de um ISO de PS2 (23/10/2026), igual ao rc_hash_ps2 do rcheevos (src/hash/rc_hash_disc.c):
MD5 do nome do executável de boot (BOOT2 do SYSTEM.CNF, sem "cdrom0:\\" e sem ";1") seguido do conteúdo dele
(no máximo 64 MB). É o que o OPL-RA calcula no PS2 no "RA: check game support"; aqui roda sem o console.

Uso: ra_hash.py <arquivo.iso>   → imprime "<hash> <executável>"
"""
import contextlib
import hashlib
import os
import struct
import sys

SETOR = 2048
MAX_BUFFER = 64 * 1024 * 1024


def _ler(f, setor, n=SETOR):
    f.seek(setor * SETOR)
    return f.read(n)


def _entradas(f, setor, tamanho):
    """(nome sem ;1 em maiúsculas, setor, tamanho, é pasta) de um diretório ISO9660."""
    dados = b''.join(_ler(f, setor + i) for i in range((tamanho + SETOR - 1) // SETOR))
    p = 0
    while p < len(dados):
        n = dados[p]
        if n == 0:   # resto do setor vazio: pula para o próximo
            p = (p // SETOR + 1) * SETOR
            continue
        reg = dados[p:p + n]
        ext, tam = struct.unpack_from('<I', reg, 2)[0], struct.unpack_from('<I', reg, 10)[0]
        nome = reg[33:33 + reg[32]].decode('latin-1').split(';')[0].upper()
        yield nome, ext, tam, bool(reg[25] & 2)
        p += n


def achar(f, caminho):
    """Setor e tamanho de um arquivo pelo caminho com '\\' (ou None)."""
    pvd = _ler(f, 16)
    raiz = pvd[156:190]
    setor, tam = struct.unpack_from('<I', raiz, 2)[0], struct.unpack_from('<I', raiz, 10)[0]
    partes = [x.upper() for x in caminho.replace('/', '\\').split('\\') if x]
    for i, parte in enumerate(partes):
        for nome, s, t, pasta in _entradas(f, setor, tam):
            if nome == parte and pasta == (i < len(partes) - 1):
                setor, tam = s, t
                break
        else:
            return None
    return setor, tam


def hash_ps2(caminho_iso):
    """caminho_iso: caminho ou arquivo já aberto (read/seek), ex.: o IsoRemoto do udpfs_nuvem.py (ISO do notebook)."""
    with (open(caminho_iso, 'rb') if isinstance(caminho_iso, (str, bytes, os.PathLike))
          else contextlib.nullcontext(caminho_iso)) as f:
        cnf = achar(f, 'SYSTEM.CNF')
        if not cnf:
            raise ValueError('SYSTEM.CNF não encontrado')
        texto = _ler(f, cnf[0], min(cnf[1], SETOR - 1)).decode('latin-1')
        exe = None
        for linha in texto.splitlines():
            chave, _, valor = linha.partition('=')
            if chave.strip().startswith('BOOT2') and valor:
                v = valor.strip()
                if v.startswith('cdrom0:'):
                    v = v[len('cdrom0:'):]
                exe = v.lstrip('\\').split(';')[0].split()[0]
                break
        if not exe:
            raise ValueError('BOOT2 não encontrado no SYSTEM.CNF')
        local = achar(f, exe)
        if not local:
            raise ValueError(f'executável {exe} não encontrado')
        setor, tam = local
        md5 = hashlib.md5(exe.encode('latin-1'))
        restante = min(tam, MAX_BUFFER)
        f.seek(setor * SETOR)
        while restante > 0:
            bloco = f.read(min(restante, 1024 * 1024))
            if not bloco:
                break
            md5.update(bloco)
            restante -= len(bloco)
        return md5.hexdigest(), exe


if __name__ == '__main__':
    h, exe = hash_ps2(sys.argv[1])
    print(h, exe)
