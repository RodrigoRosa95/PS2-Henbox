#!/usr/bin/env python3
"""Servidor de kits online da comunidade (pedido do usuário 24/10/2026) — porta 8792.

Um kit é o que falta para um jogo de PS2 entrar online, SEM o jogo: VMC já configurado (perfil de rede/DNS), CFG do
OPL (modo de compatibilidade, VMC ligado), patch PPF (quando o servidor exige o jogo modificado), capa e o DNS do
servidor comunitário. Cada um usa o ISO do próprio disco; a central da TV box (central.py) confere a versão pelo hash
do RetroAchievements e aplica o kit no pendrive.

ISO não entra: a pirataria de jogo comercial fica de fora (mesma regra da Loja SNES). O envio confere cada arquivo
(VMC pela assinatura do memory card, PPF pelo cabeçalho, CFG texto curto, imagem pequena) e recusa qualquer coisa com
cara de ISO (CD001 no setor 16). O kit enviado fica em pendentes/ até alguém aprovar:
  kits_servidor.py pendentes            lista o que chegou
  kits_servidor.py aprovar <n> [id]     publica (id padrão: código-do-jogo + número)
  kits_servidor.py recusar <n>
  kits_servidor.py testado <id> [data]  marca "testado online em <data>"
Pastas: ~/ps2-monitor/kits/{aprovados,pendentes}; catálogo montado de aprovados/<id>/kit.json.
Uso: kits_servidor.py [porta]
"""
import base64, hashlib, json, os, re, shutil, sys, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

BASE = os.environ.get('KITS_DIR', os.path.expanduser('~/ps2-monitor/kits'))
APROVADOS, PENDENTES = os.path.join(BASE, 'aprovados'), os.path.join(BASE, 'pendentes')
CODIGO = re.compile(r'^[A-Z]{4}_\d{3}\.\d{2}$')
IP = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
LIMITE_TOTAL = 100 << 20
LIMITES = {'vmc': 64 << 20 | 1 << 22, 'cfg': 64 << 10, 'ppf': 64 << 20, 'capa': 2 << 20, 'txt': 64 << 10}


def log(*a):
    print(time.strftime('%d/%m %H:%M:%S'), *a, flush=True)


class Recusado(Exception):
    pass


def tipo_do_arquivo(nome, d):
    """Confere o conteúdo (não só a extensão) e devolve vmc | cfg | ppf | capa | txt."""
    ext = os.path.splitext(nome)[1].lower()
    if len(d) > 0x8006 and d[0x8001:0x8006] == b'CD001':
        raise Recusado(f'{nome}: é um ISO — a central só aceita VMC, CFG, patch e imagens, nunca o jogo')
    if ext in ('.bin', '.mc2', '.ps2') and d.startswith(b'Sony PS2 Memory Card Format '):
        tipo = 'vmc'
    elif ext == '.ppf' and d[:5] in (b'PPF10', b'PPF20', b'PPF30'):
        tipo = 'ppf'
    elif ext == '.cfg':
        tipo = 'cfg'
        texto = d.decode('latin-1')
        if any(ord(c) < 9 for c in texto) or not all('=' in l for l in texto.splitlines() if l.strip()):
            raise Recusado(f'{nome}: não parece um CFG do OPL (linhas chave=valor)')
    elif ext in ('.jpg', '.jpeg', '.png'):
        tipo = 'capa'
        try:
            from PIL import Image
            Image.open(BytesIO(d)).verify()
        except Exception:
            raise Recusado(f'{nome}: imagem inválida')
    elif ext in ('.txt', '.md'):
        tipo = 'txt'
        d.decode('utf-8')
    else:
        raise Recusado(f'{nome}: tipo não aceito (VMC .bin, .cfg, .ppf, .jpg/.png, .txt)')
    if len(d) > LIMITES[tipo]:
        raise Recusado(f'{nome}: grande demais para {tipo}')
    return tipo


def nome_seguro(n):
    n = os.path.basename(str(n or '')).strip()
    n = re.sub(r'[^\w.\- ()]', '_', n)[:80]
    if not n or n.startswith('.'):
        raise Recusado('nome de arquivo inválido')
    return n


def receber_kit(dados):
    cod = str(dados.get('codigo', '')).upper().replace('-', '_')
    if not CODIGO.match(cod):
        raise Recusado('código do jogo inválido (ex.: SLUS_203.12)')
    if dados.get('dns') and not IP.match(str(dados['dns'])):
        raise Recusado('DNS deve ser um IP (ex.: 45.7.228.197)')
    arqs, total = [], 0
    for a in dados.get('arquivos', [])[:8]:
        nome = nome_seguro(a.get('nome'))
        d = base64.b64decode(a.get('dados', ''), validate=True)
        total += len(d)
        if total > LIMITE_TOTAL:
            raise Recusado('kit grande demais (máximo 100 MB)')
        arqs.append((nome, tipo_do_arquivo(nome, d), d))
    if not arqs and not dados.get('dns'):
        raise Recusado('kit vazio: mande ao menos um VMC, CFG, patch ou o DNS')
    os.makedirs(PENDENTES, exist_ok=True)
    n = 1 + max([int(x) for x in os.listdir(PENDENTES) if x.isdigit()] + [0])
    pasta = os.path.join(PENDENTES, str(n))
    os.makedirs(pasta)
    meta = {'codigo': cod, 'titulo': str(dados.get('titulo', ''))[:80], 'dns': dados.get('dns') or '',
            'servidor': str(dados.get('servidor', ''))[:80], 'notas': str(dados.get('notas', ''))[:2000],
            'autor': str(dados.get('autor', ''))[:40], 'vmc_nome': '', 'versoes': [], 'arquivos': [],
            'enviado': time.strftime('%d/%m/%Y %H:%M')}
    for v in dados.get('versoes', [])[:4]:
        if re.match(r'^[0-9a-f]{32}$', str(v.get('ra_hash', ''))):
            meta['versoes'].append({'ra_hash': v['ra_hash'], 'nome': str(v.get('nome', ''))[:40]})
    for nome, tipo, d in arqs:
        with open(os.path.join(pasta, nome), 'wb') as f:
            f.write(d)
        meta['arquivos'].append({'nome': nome, 'tipo': tipo, 'tam': len(d), 'sha256': hashlib.sha256(d).hexdigest()})
        if tipo == 'vmc' and not meta['vmc_nome']:
            meta['vmc_nome'] = nome
    with open(os.path.join(pasta, 'kit.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f'kit novo para aprovar: pendentes/{n} {cod} {meta["titulo"]} ({len(arqs)} arquivo(s))')
    return n


def catalogo():
    kits = []
    for id_ in sorted(os.listdir(APROVADOS)) if os.path.isdir(APROVADOS) else []:
        try:
            with open(os.path.join(APROVADOS, id_, 'kit.json'), encoding='utf-8') as f:
                k = json.load(f)
        except (OSError, ValueError):
            continue
        k['id'] = id_
        kits.append(k)
    return {'kits': kits, 'gerado': time.time()}


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def responder(self, d, tipo='application/json', codigo=200):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(d)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(d)

    def json(self, obj, codigo=200):
        self.responder(json.dumps(obj, ensure_ascii=False).encode(), codigo=codigo)

    def do_GET(self):
        u = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if u == '/kits/catalogo.json':
            return self.json(catalogo())
        m = re.match(r'^/kits/([\w.\-]+)/([^/]+)$', u)
        if m and m.group(2) != 'kit.json':
            cam = os.path.join(APROVADOS, m.group(1), m.group(2))
            if os.path.isfile(cam) and os.path.realpath(cam).startswith(os.path.realpath(APROVADOS) + os.sep):
                return self.responder(open(cam, 'rb').read(), 'application/octet-stream')
        return self.json({'erro': 'não encontrado'}, 404)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != '/kits/enviar':
            return self.json({'erro': 'não encontrado'}, 404)
        n = int(self.headers.get('Content-Length') or 0)
        if n > LIMITE_TOTAL * 4 // 3 + (1 << 20):
            return self.json({'erro': 'kit grande demais (máximo 100 MB)'}, 413)
        try:
            k = receber_kit(json.loads(self.rfile.read(n)))
            return self.json({'ok': True, 'numero': k, 'msg': 'Kit recebido! Ele aparece na central depois de aprovado.'})
        except (Recusado, ValueError, UnicodeDecodeError) as e:
            return self.json({'erro': str(e)}, 400)


def cli(args):
    if args[0] == 'pendentes':
        for n in sorted(os.listdir(PENDENTES) if os.path.isdir(PENDENTES) else [], key=lambda x: int(x) if x.isdigit() else 0):
            k = json.load(open(os.path.join(PENDENTES, n, 'kit.json'), encoding='utf-8'))
            print(f'{n}: {k["codigo"]} {k["titulo"]} — {", ".join(a["nome"] for a in k["arquivos"]) or "só DNS"}'
                  f'{" DNS " + k["dns"] if k["dns"] else ""} (por {k["autor"] or "?"}, {k["enviado"]})')
    elif args[0] == 'aprovar':
        k = json.load(open(os.path.join(PENDENTES, args[1], 'kit.json'), encoding='utf-8'))
        id_ = args[2] if len(args) > 2 else f'{k["codigo"]}-{args[1]}'
        os.makedirs(APROVADOS, exist_ok=True)
        shutil.move(os.path.join(PENDENTES, args[1]), os.path.join(APROVADOS, id_))
        print('publicado como', id_)
    elif args[0] == 'recusar':
        shutil.rmtree(os.path.join(PENDENTES, args[1]))
        print('apagado')
    elif args[0] == 'testado':
        cam = os.path.join(APROVADOS, args[1], 'kit.json')
        k = json.load(open(cam, encoding='utf-8'))
        k['testado'] = args[2] if len(args) > 2 else time.strftime('%d/%m/%Y')
        json.dump(k, open(cam, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('marcado testado em', k['testado'])


if __name__ == '__main__':
    if len(sys.argv) > 1 and not sys.argv[1].isdigit():
        cli(sys.argv[1:])
        sys.exit()
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
    for d in (APROVADOS, PENDENTES):
        os.makedirs(d, exist_ok=True)
    log(f'kits online em http://0.0.0.0:{porta}/kits/catalogo.json ({BASE})')
    ThreadingHTTPServer(('0.0.0.0', porta), H).serve_forever()
