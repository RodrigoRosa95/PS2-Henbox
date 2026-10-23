#!/usr/bin/env python3
"""Baixa do repositório oficial do Termux os .deb do Python + Pillow com TODAS as dependências (23/10/2026), para o
instalador pôr o Python na TV box sem internet (o "pkg install" era o passo que mais falhava em casa de terceiros).
  baixar_python.py [arquitetura...]     padrão: arm aarch64   → python-<arq>/*.deb + python-<arq>/LISTA
O instalador manda a pasta da arquitetura da box e roda "dpkg -i *.deb" dentro do Termux; se falhar, cai no pkg.
Os pacotes são do Termux (licenças em cada .deb, a maioria livre: Python PSF, Pillow HPND...)."""
import gzip, hashlib, os, re, sys, urllib.request

REPO = 'https://packages-cf.termux.dev/apt/termux-main'
PEDIDOS = ['python', 'python-pillow']
PASTA = os.path.dirname(os.path.abspath(__file__))


def baixar(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'henbox'}), timeout=120) as r:
        return r.read()


def pacotes(arq):
    texto = gzip.decompress(baixar(f'{REPO}/dists/stable/main/binary-{arq}/Packages.gz')).decode()
    todos = {}
    for bloco in texto.split('\n\n'):
        c = dict(re.findall(r'^([\w-]+): (.*)$', bloco, re.M))
        if 'Package' in c:
            todos[c['Package']] = c
    return todos


def dependencias(todos, nomes):
    feitos, fila = [], list(nomes)
    prov = {}
    for p, c in todos.items():
        for v in re.split(r',\s*', c.get('Provides', '')):
            if v:
                prov.setdefault(v.split()[0], p)
    while fila:
        n = fila.pop(0)
        n = n if n in todos else prov.get(n, n)
        if n in feitos:
            continue
        if n not in todos:
            raise SystemExit(f'pacote {n} não existe no repositório')
        feitos.append(n)
        for campo in ('Depends', 'Pre-Depends'):
            for d in re.split(r',\s*', todos[n].get(campo, '')):
                if d:
                    fila.append(d.split('|')[0].split()[0].strip())   # "a | b": a primeira opção
    return feitos


def main():
    for arq in sys.argv[1:] or ['arm', 'aarch64']:
        todos = pacotes(arq)
        nomes = dependencias(todos, PEDIDOS)
        dest = os.path.join(PASTA, f'python-{arq}')
        os.makedirs(dest, exist_ok=True)
        lista, total = [], 0
        for n in nomes:
            c = todos[n]
            arquivo = os.path.join(dest, os.path.basename(c['Filename']))
            if not (os.path.exists(arquivo) and hashlib.sha256(open(arquivo, 'rb').read()).hexdigest() == c['SHA256']):
                dados = baixar(f"{REPO}/{c['Filename']}")
                if hashlib.sha256(dados).hexdigest() != c['SHA256']:
                    raise SystemExit(f'sha256 não confere: {n}')
                open(arquivo, 'wb').write(dados)
            lista.append(os.path.basename(arquivo))
            total += os.path.getsize(arquivo)
        for velho in os.listdir(dest):   # versões antigas saem
            if velho.endswith('.deb') and velho not in lista:
                os.remove(os.path.join(dest, velho))
        open(os.path.join(dest, 'LISTA'), 'w').write('\n'.join(lista) + '\n')
        print(f'{arq}: {len(lista)} pacotes, {total >> 20} MB')


if __name__ == '__main__':
    main()
