#!/usr/bin/env python3
"""Atualização automática da TV box (PS2 Henbox, 23/10/2026). Chamado pelo iniciar.sh; confere na hora e depois a
cada 24 h se a pasta downloads/ do GitHub tem pacote mais novo que ~/ps2nav/VERSAO:
  downloads/ps2nav-versao.txt          "AAAAMMDD-HHMM SHA256"  (gerar-pacote.sh com PUBLICO=1)
  downloads/ps2nav-atualizacao.tar.gz  ps2nav/ (sem config.json), udpfs_server/ e boot/
Se tiver, baixa, confere o sha256, copia por cima mantendo config.json/logs/ps2 do usuário e reinicia os serviços.
O navegador.elf do pendrive do PS2 se atualiza sozinho depois (navegador_servidor.verificar_pendrive).
Desligar: "atualizar": false no config.json (a box do autor, que roda versões de teste)."""
import hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request

PASTA = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(PASTA)
BASE = 'https://raw.githubusercontent.com/RodrigoRosa95/PS2-Henbox/main/downloads/'


def log(*a):
    print(time.strftime('%d/%m %H:%M:%S'), *a, flush=True)


def baixar(nome, timeout=60):
    req = urllib.request.Request(BASE + nome, headers={'User-Agent': 'ps2-henbox', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ligado():
    try:
        return json.load(open(os.path.join(PASTA, 'config.json'))).get('atualizar', True) is not False
    except (OSError, ValueError):
        return True


def conferir():
    if not ligado():
        log('atualização automática desligada no config.json')
        return False
    local = open(os.path.join(PASTA, 'VERSAO')).read().strip() if os.path.exists(os.path.join(PASTA, 'VERSAO')) else ''
    try:
        nova, sha = baixar('ps2nav-versao.txt', 20).decode().split()[:2]
    except Exception as e:
        log('sem acesso ao GitHub agora:', e)
        return False
    if nova <= local:
        log(f'em dia ({local})')
        return False
    log(f'versão nova {nova} (esta: {local or "?"}), baixando…')
    dados = baixar('ps2nav-atualizacao.tar.gz', 300)
    if hashlib.sha256(dados).hexdigest() != sha:
        log('erro: sha256 do pacote não confere, nada mudou')
        return False
    tmp = tempfile.mkdtemp(dir=HOME)
    try:
        arq = os.path.join(tmp, 'p.tar.gz')
        open(arq, 'wb').write(dados)
        with tarfile.open(arq) as t:
            for m in t.getmembers():   # só caminhos relativos dentro das 3 pastas do pacote
                if m.name.startswith('/') or '..' in m.name.split('/') or m.name.split('/')[0] not in (
                        'ps2nav', 'udpfs_server', 'boot') or m.issym() or m.islnk():
                    raise ValueError('pacote com caminho estranho: ' + m.name)
            t.extractall(tmp)
        novo = os.path.join(tmp, 'ps2nav')
        if os.path.exists(os.path.join(novo, 'config.json')):
            os.remove(os.path.join(novo, 'config.json'))   # o do usuário fica
        shutil.copytree(novo, PASTA, dirs_exist_ok=True)
        if os.path.isdir(os.path.join(tmp, 'udpfs_server')):
            shutil.copytree(os.path.join(tmp, 'udpfs_server'), os.path.join(HOME, 'udpfs_server'), dirs_exist_ok=True)
        boot = os.path.join(HOME, '.termux', 'boot')
        for nome, destino in (('ps2nav', 'ps2nav'), ('udpfs-ps2.sh', 'udpfs-ps2.sh')):
            if os.path.exists(os.path.join(tmp, 'boot', nome)):
                os.makedirs(boot, exist_ok=True)
                if os.path.lexists(os.path.join(boot, destino)):
                    os.remove(os.path.join(boot, destino))
                shutil.copy(os.path.join(tmp, 'boot', nome), os.path.join(boot, destino))
                os.chmod(os.path.join(boot, destino), 0o755)
        for sh in os.listdir(PASTA):
            if sh.endswith('.sh'):
                os.chmod(os.path.join(PASTA, sh), 0o755)
    except Exception as e:
        log('erro aplicando a atualização:', e)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    subprocess.run([sys.executable, os.path.join(PASTA, 'configurar.py'), 'aplicar'], cwd=PASTA)
    log(f'atualizado para {nova}; reiniciando os serviços')
    return True


if __name__ == '__main__':
    while True:
        if conferir():
            subprocess.Popen(['bash', os.path.join(PASTA, 'iniciar.sh')], cwd=PASTA, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break   # o iniciar.sh liga outro atualizar.py
        time.sleep(24 * 3600)
