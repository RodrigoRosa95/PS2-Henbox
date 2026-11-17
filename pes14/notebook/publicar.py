#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
"""Publica o save atualizado do PES 14 em a pasta PUBLICAR (veja caminhos.py), que o servidor HTTP da rede serve em /pes14/.

Só vai o Option File: os arquivos de ícone do save não mudam e não precisam ser regravados no cartão.
O manifesto leva versão, tamanho e sha256 de cada arquivo e um resumo para a página da TV box.
"""
import hashlib, json, os, shutil, sys, time

SAVE = 'BESLES-556762014OPT'
ORIGEM = BASE+'/novo'
DESTINO = PUBLICAR


def sha256(c):
    h = hashlib.sha256()
    with open(c, 'rb') as f:
        for b in iter(lambda: f.read(1 << 16), b''):
            h.update(b)
    return h.hexdigest()


def publicar(resumo=None, versao=None):
    try:   # conteúdo igual ao já publicado: mantém a versão (a box não vê novidade onde não há)
        ant = json.load(open(os.path.join(DESTINO, 'manifest.json'), encoding='utf-8'))
        if ant['arquivos'][0]['sha256'] == sha256(os.path.join(ORIGEM, SAVE)):
            versao = versao or ant['versao']
    except (OSError, ValueError, KeyError, IndexError):
        pass
    versao = versao or time.strftime('%Y%m%d-%H%M')
    pasta = os.path.join(DESTINO, SAVE)
    os.makedirs(pasta, exist_ok=True)
    arq = os.path.join(ORIGEM, SAVE)
    shutil.copy2(arq, os.path.join(pasta, SAVE + '.tmp'))
    os.replace(os.path.join(pasta, SAVE + '.tmp'), os.path.join(pasta, SAVE))   # troca de uma vez: a box nunca lê pela metade
    manifesto = {
        'versao': versao,
        'pasta': SAVE,
        'gerado': time.strftime('%d/%m/%Y %H:%M'),
        'arquivos': [{'nome': SAVE, 'tam': os.path.getsize(arq), 'sha256': sha256(arq)}],
        'resumo': resumo or {},
    }
    tmp = os.path.join(DESTINO, 'manifest.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(DESTINO, 'manifest.json'))   # o manifesto por último
    return manifesto


if __name__ == '__main__':
    m = publicar()
    print(json.dumps(m, ensure_ascii=False)[:300])
