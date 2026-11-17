#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
"""Atualiza o save do PES 14 sozinho: raspa os elencos do Transfermarkt → casa com os jogadores do jogo → gera o Option File
→ publica na pasta PUBLICAR (a TV box baixa de lá). Se algo sair estranho, NÃO publica e deixa a versão anterior.

Uso: atualizar_tudo.py [--sem-raspar]   (--sem-raspar reaproveita os elencos já baixados)
Base: original/ (o seu Option File do PS2, copiado uma vez). As transferências são aplicadas sobre ele.
"""
import json, os, subprocess, sys, time, traceback
D = BASE
sys.path.insert(0, D)
AQUI = os.path.dirname(os.path.abspath(__file__))
LOG = open(D + '/atualizar.log', 'a')


def log(*a):
    t = time.strftime('%d/%m %H:%M:%S ') + ' '.join(str(x) for x in a)
    print(t, flush=True); LOG.write(t + '\n'); LOG.flush()


def main():
    if '--sem-raspar' not in sys.argv:
        log('raspando os elencos do Transfermarkt (~7 min)')
        for f in ('elencos.json',):
            if os.path.exists(f'{D}/tm/{f}'): os.replace(f'{D}/tm/{f}', f'{D}/tm/{f}.anterior')
        r = subprocess.run([sys.executable, os.path.join(AQUI, 'raspar.py')], capture_output=True, text=True, timeout=3000)
        if r.returncode != 0:
            raise RuntimeError('raspagem falhou: ' + r.stderr[-300:])
    subprocess.run([sys.executable, os.path.join(AQUI, 'parse2.py')], check=True, capture_output=True, timeout=600)
    E2 = json.load(open(D + '/tm/elencos2.json'))
    com_jogadores = sum(1 for c in E2.values() if len(c['jogadores']) >= 10)
    total = sum(len(c['jogadores']) for c in E2.values())
    log(f'elencos: {com_jogadores} clubes com 10+ jogadores, {total} jogadores')
    if com_jogadores < 100 or total < 2500:
        raise RuntimeError('o Transfermarkt veio incompleto: não publico nada')
    import casar3, gerar, publicar
    pares, stat = casar3.casar()
    json.dump(pares, open(D + '/tm/pares.json', 'w'), ensure_ascii=False)
    log('casamento:', dict(stat))
    if stat['ok'] < 100:
        raise RuntimeError('poucos jogadores casaram: não publico nada')
    novo, lg, feitos = gerar.gerar()
    json.dump(lg, open(D + '/log_geracao.json', 'w'), ensure_ascii=False)
    ok = [l for l in lg if l[0] == 'OK']
    if len(ok) < 50:
        raise RuntimeError('transferências demais recusadas: não publico nada')
    resumo = {'transferencias': len(ok), 'sem_vaga': sum(1 for l in lg if l[0] == 'CHEIO'),
              'exemplos': [f'{l[1]}: {", ".join(l[2]) or "sem clube"} → {l[3]}' for l in ok[:12]]}
    m = publicar.publicar(resumo)
    log('publicado', m['versao'], m['arquivos'][0]['sha256'][:12], f'{len(ok)} transferências')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('FALHOU:', repr(e)); log(traceback.format_exc()[-400:]); sys.exit(1)
