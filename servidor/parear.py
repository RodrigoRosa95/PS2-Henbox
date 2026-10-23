#!/usr/bin/env python3
"""Pareamento do servidor em nuvem com o app PS2 Henbox (23/10/2026): mostra um QR (e o link) henbox://parear com o
endereço e a chave. No celular, a câmera lê o QR, o app PS2 Henbox abre com tudo preenchido e salva na TV box.
  servidor/parear.py [ENDEREÇO]     ex.: http://192.168.0.10:8781 (padrão: o IP deste PC na porta 8781)
  --esperar                         (Docker) espera a chave existir antes
A chave dá acesso à coleção: mostre o QR só para quem você quer."""
import os, socket, sys, time, urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = os.environ.get('PS2_CHAVE_ARQ') or os.path.join(RAIZ, 'navegador', 'videos_https.chave')


def meu_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('1.1.1.1', 80))   # não envia nada: só escolhe a interface de saída
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--esperar' in sys.argv:
        for _ in range(60):
            if os.path.exists(ARQ):
                break
            time.sleep(1)
    chave = open(ARQ).read().strip()
    url = (args[0] if args else os.environ.get('PS2_ENDERECO')) or f'http://{meu_ip()}:8781'
    link = 'henbox://parear?' + urllib.parse.urlencode({'url': url, 'chave': chave})
    print('\n===== PAREAR com o app PS2 Henbox =====')
    print('Leia o QR com a câmera do celular (com o app PS2 Henbox instalado), ou digite no app:')
    print(f'  Endereço: {url}\n  Chave:    {chave}')
    try:
        import qrcode
        q = qrcode.QRCode(border=2)
        q.add_data(link)
        q.print_ascii(invert=True)
    except ImportError:
        print('(sem o módulo qrcode para desenhar o QR: pip install qrcode)')
    print('Link:', link)
    if '172.' in url and os.path.exists('/.dockerenv'):
        print('Aviso: dentro do Docker o IP acima é o do contêiner; rode com PS2_ENDERECO=http://IP_DO_PC:8781')
    print('=======================================\n', flush=True)


if __name__ == '__main__':
    main()
