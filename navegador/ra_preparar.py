#!/usr/bin/env python3
"""Prepara as conquistas de um jogo sem o PS2 (23/10/2026): faz aqui o "RA: check game support" do OPL-RA.

1. hash RetroAchievements do ISO (ra_hash.py, igual ao do console);
2. pede a lista de endereços ao app xeRAbora (UDP 18194) com o mesmo protocolo do console
   (client/src/protocol.h do xerabora): RAQ1 <hash> <serial> <ip> <porta> → RAA1 WAIT | OK <bytes> <pedaços> | NO;
   RAG1 <hash> <n> <ip> <porta> → RAC1 <n> <tamanho> <dados>;
3. grava a lista como <pasta>/<serial>.wl — os mesmos bytes que o OPL-RA grava em RA/<serial>.wl.
O navegador copia o .wl para mass:/RA/ no pendrive do PS2, onde o OPL-RA procura primeiro ao abrir o jogo.

Uso: ra_preparar.py <arquivo.iso> <serial> <pasta de saída> [ip do xeRAbora]
"""
import os
import re
import socket
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from ra_hash import hash_ps2  # noqa: E402

PORTA_XERABORA = 18194
ESPERA_IDENTIFICAR = 60   # o app consulta o servidor do RetroAchievements antes de responder OK


def _meu_ip(destino):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((destino, PORTA_XERABORA))
        return s.getsockname()[0]
    finally:
        s.close()


def preparar(iso, serial, pasta, xerabora='127.0.0.1', log=print):
    """Devolve (caminho do .wl, texto para mostrar). Levanta ValueError com a explicação se não der."""
    h, exe = hash_ps2(iso)
    log(f'hash {h} ({exe})')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', 0))
    sock.settimeout(2)
    ip, porta = _meu_ip(xerabora), sock.getsockname()[1]
    destino = (xerabora, PORTA_XERABORA)
    try:
        fim = time.time() + ESPERA_IDENTIFICAR
        resposta = None
        while time.time() < fim:
            sock.sendto(f'RAQ1 {h} {serial} {ip} {porta}'.encode(), destino)
            try:
                dados, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            texto = dados.split(b'\0', 1)[0].decode('latin-1').strip()
            if texto.startswith('RAA1 WAIT'):
                time.sleep(1)
                continue
            resposta = texto
            break
        if resposta is None:
            raise ValueError('o app xeRAbora não respondeu (está aberto e com login na TV box?)')
        if resposta.startswith('RAA1 NO'):
            raise ValueError('o RetroAchievements não conhece este ISO: ' + resposta[7:].strip())
        m = re.match(r'RAA1 OK (\d+) (\d+)(?: (\d+) (\d+) (\d+) ?(.*))?', resposta)
        if not m:
            raise ValueError('resposta inesperada do xeRAbora: ' + resposta[:80])
        total, pedacos = int(m.group(1)), int(m.group(2))
        titulo = (m.group(6) or '').strip()
        log(f'lista: {total} bytes em {pedacos} pedaços — {titulo}')
        lista = {}
        for _ in range(5):   # UDP: repete os pedaços que não chegaram
            for n in range(pedacos):
                if n not in lista:
                    sock.sendto(f'RAG1 {h} {n} {ip} {porta}'.encode(), destino)
            prazo = time.time() + 3
            while len(lista) < pedacos and time.time() < prazo:
                try:
                    dados, _ = sock.recvfrom(2048)
                except socket.timeout:
                    break
                cab = re.match(rb'RAC1 (\d+) (\d+) ', dados)
                if cab:
                    n, tam = int(cab.group(1)), int(cab.group(2))
                    lista[n] = dados[cab.end():cab.end() + tam]
            if len(lista) == pedacos:
                break
        if len(lista) < pedacos:
            raise ValueError(f'chegaram só {len(lista)} de {pedacos} pedaços da lista')
        wl = b''.join(lista[n] for n in range(pedacos))
        if len(wl) != total:
            raise ValueError(f'lista com {len(wl)} bytes, esperado {total}')
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, serial + '.wl')
        with open(caminho + '.tmp', 'wb') as f:
            f.write(wl)
        os.replace(caminho + '.tmp', caminho)
        conquistas = f' — {m.group(3)} conquistas' if m.group(3) else ''
        return caminho, f'{titulo or serial}{conquistas}'
    finally:
        sock.close()


if __name__ == '__main__':
    caminho, texto = preparar(sys.argv[1], sys.argv[2], sys.argv[3], *(sys.argv[4:5] or []))
    print(caminho, '|', texto)
