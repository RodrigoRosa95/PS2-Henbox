#!/usr/bin/env python3
"""Navegador do PS2 — lado do notebook (pedido do usuário 16/10/2026: "faça o PS2 abrir o sistema-mobile-3004").

O PS2 roda ps2/navegador.elf (cliente magro). Aqui um Chromium sem janela abre a página; cada repintura
(Page.screencastFrame do DevTools) vira retângulos RGBX comprimidos com zlib (só as faixas que mudaram) gravados em
ps2/dif.bin e ps2/completa.bin, que o PS2 lê pelo host: do PS2Link (o ps2client fica servindo a pasta ps2/); o PS2
escreve o controle em ps2/entrada.bin. Formato em ps2/navegador.c. Rede própria (TCP 8771) falhou neste PS2.

Controle no PS2:
  analógico esquerdo / direcional  move o cursor        X  clica
  analógico direito / L1 / R1      rola a página         O  volta (ou fecha o teclado)
  quadrado                         abre/fecha teclado    triângulo  recarrega
  START                            página inicial        SELECT+START  sai do navegador (volta ao PS2Link)
  L2                               sistema (3004)        R2         loja de jogos
O teclado virtual é desenhado aqui por cima da página e abre sozinho ao clicar num campo de texto.
A página é mostrada com zoom 1,5 (viewport 427x299) para o texto ficar legível na TV; loja e cinema (porta 8770,
feitos para o PS2) ficam em 1,0 = 640x448 nativo (pedido do usuário 17/10/2026: menu da loja grande demais).
Perfil do Chromium em ./perfil: o login feito uma vez no PS2 fica guardado.
"""
import json, os, socket, struct, subprocess, sys, threading, time, urllib.request, zlib
from io import BytesIO
from base64 import b64decode

import websocket
from PIL import Image, ImageChops, ImageDraw, ImageFont

PASTA = os.path.dirname(os.path.abspath(__file__))
WEB = os.environ.get('PS2_NAV_WEB', '127.0.0.1')   # onde estão o sistema (3004) e o ps2-web (8770); na TV box: o notebook
INICIO = os.environ.get('PS2_NAV_INICIO', f'http://{WEB}:3004/')
LOJA = os.environ.get('PS2_NAV_LOJA', f'http://{WEB}:8770/loja.html')   # TV box: a loja da videos.py (8780/loja/)
CINEMA_PAG = f'http://{WEB}:8770/cinema.html'
# TV box (17/10/2026): em vez de abrir o Chrome, conecta no WebView do app PS2 Navegador (tvbox-app/): DevTools pela
# ponte 127.0.0.1:9222 e a imagem crua da tela virtual por 127.0.0.1:9223 (o captureScreenshot do WebView 74 não
# entrega quadro). O zoom 1,5 vira CSS (a emulação do WebView só encolhe a área, não amplia).
CDP_EXTERNO = os.environ.get('PS2_NAV_CDP')         # ex.: 127.0.0.1:9222
QUADROS = os.environ.get('PS2_NAV_QUADROS')         # ex.: 127.0.0.1:9223
PORTA_CONTROLE = 8772   # local: "sair" fecha o navegador no PS2 (volta ao PS2Link), "status", "loja", "sistema"
LARG, ALT, ZOOM = 640, 448, 1.5
ZOOM_PS2 = 1.0   # páginas do ps2-web (loja.html, cinema.html), já desenhadas para 640x448


def zoom_para(url):
    return ZOOM_PS2 if (':8770/' in url or ':8780/' in url) else ZOOM   # 8780: videos.py da TV box
PORTA_CDP = 9333
PASTA_PS2 = os.path.join(PASTA, 'ps2')   # servida ao PS2 pelo ps2client (host:)
MUSICA = 0x100                            # bit do cmd: tocar ps2/musica.raw (sons/gerar_sons.py)
PEDIDO = 0x200                            # bit do cmd: há cópia em ps2/pedido.bin (ROM → pendrive do PS2)
ESTADOS_PEDIDO = {1: 'copiando', 2: 'pronto', 3: 'o PS2 não carregou o driver de pendrive',
                  4: 'erro lendo a ROM do notebook', 5: 'pendrive não encontrado no PS2 (ou sem espaço)',
                  6: 'erro gravando no pendrive', 7: 'abrindo no PS2', 8: 'tocando', 9: 'vídeo acabou',
                  10: 'vídeo parado'}
CINEMA = os.environ.get('PS2_NAV_CINEMA', f'http://{WEB}:8770/api/cinema/')   # vazio: sem Cinema (TV box)   # cinema.py (servidor ps2-web): pular / parado
RA_ELF = 'SNESticle.elf'                              # SNESticle Revive com ROM por argv e DS4 (ps2/snesticle/ORIGEM.txt);
#                                                         o RetroArch dava tela preta no PS2 real (17/10/2026)
RA_PASTA = 'mass:/APPS/SNESTICLE'                       # no pendrive; title.cfg faz aparecer no OPL → Apps
# teclas especiais do teclado USB (o PS2 manda 0x80|código): código → (key, code, windowsVirtualKeyCode)
ESPECIAIS_USB = {0x29: ('ArrowRight', 'ArrowRight', 39), 0x2a: ('ArrowLeft', 'ArrowLeft', 37),
                 0x2b: ('ArrowDown', 'ArrowDown', 40), 0x2c: ('ArrowUp', 'ArrowUp', 38),
                 0x24: ('Home', 'Home', 36), 0x25: ('PageUp', 'PageUp', 33), 0x26: ('Delete', 'Delete', 46),
                 0x27: ('End', 'End', 35), 0x28: ('PageDown', 'PageDown', 34), 0x1b: ('Escape', 'Escape', 27)}
FAIXA = 16
def _fonte(nome, tam):   # Ubuntu ou a pasta fontes/ ao lado (TV box/Termux)
    for d in ('/usr/share/fonts/truetype/dejavu', os.path.join(PASTA, 'fontes')):
        if os.path.exists(os.path.join(d, nome)):
            return ImageFont.truetype(os.path.join(d, nome), tam)
    return ImageFont.load_default()
FONTE = _fonte('DejaVuSans-Bold.ttf', 22)
FONTE_P = _fonte('DejaVuSans.ttf', 15)

B = dict(SELECT=0x0001, START=0x0008, UP=0x0010, RIGHT=0x0020, DOWN=0x0040, LEFT=0x0080, L2=0x0100, R2=0x0200,
         L1=0x0400, R1=0x0800, TRIANGULO=0x1000, CIRCULO=0x2000, X=0x4000, QUADRADO=0x8000)


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


# ---------------- Chromium (DevTools) ----------------
class Chromium:
    def __init__(self):
        cdp = CDP_EXTERNO or f'127.0.0.1:{PORTA_CDP}'
        if not CDP_EXTERNO:
            exe = next(p for p in ('/usr/bin/google-chrome', '/usr/bin/chromium') if os.path.exists(p))
            self.proc = subprocess.Popen([exe, '--headless=new', f'--remote-debugging-port={PORTA_CDP}',
                                          '--remote-allow-origins=*', f'--user-data-dir={PASTA}/perfil',
                                          f'--window-size={LARG},{ALT}', '--hide-scrollbars', '--no-first-run',
                                          '--disable-gpu', '--lang=pt-BR', 'about:blank'],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                alvos = json.load(urllib.request.urlopen(f'http://{cdp}/json', timeout=2))
                pag = next(a for a in alvos if a['type'] == 'page')
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError('Chromium não abriu')
        self.ws = websocket.create_connection(pag['webSocketDebuggerUrl'], timeout=None, suppress_origin=True)
        self.n, self.respostas, self.trava = 0, {}, threading.Lock()
        self.ao_quadro = None
        self.url = ''
        threading.Thread(target=self._ler, daemon=True).start()
        self.cmd('Page.enable')
        self.zoom = None
        if QUADROS:   # WebView: viewport fica 640x448 (mouse sem divisão); a página amplia a si mesma por CSS
            self.zoom = 1.0
            self.cmd('Emulation.clearDeviceMetricsOverride')   # sobra de outra conexão encolheria a área
            self.cmd('Page.addScriptToEvaluateOnNewDocument', source=(
                "(function(){var z=(location.port=='8770'||location.port=='8780')?%s:%s;function f(){if(document.documentElement)"
                "document.documentElement.style.zoom=z}f();document.addEventListener('DOMContentLoaded',f)})()"
                % (ZOOM_PS2, ZOOM)))
            self.num_quadro = -1
            threading.Thread(target=self._vigiar_quadros, daemon=True).start()
        else:
            self.ajustar_zoom(INICIO, esperar=True)
            self.cmd('Page.startScreencast', format='png', maxWidth=LARG, maxHeight=ALT, everyNthFrame=1)
        self.cmd('Page.navigate', url=INICIO)

    def _quadro_webview(self):
        """Último quadro da tela virtual do app: "PSW1" num:u32 larg:u16 alt:u16 + RGBA."""
        h, p = QUADROS.rsplit(':', 1)
        with socket.create_connection((h, int(p)), timeout=5) as s:
            b = bytearray()
            while True:
                d = s.recv(1 << 20)
                if not d:
                    break
                b += d
        num, w, a = struct.unpack('<IHH', b[4:12])
        return num, Image.frombuffer('RGBA', (w, a), bytes(b[12:]), 'raw', 'RGBA', 0, 1).convert('RGB')

    def _vigiar_quadros(self):
        """No lugar do screencast: pega o quadro novo da tela virtual ~12 vezes por segundo."""
        while True:
            try:
                num, img = self._quadro_webview()
                if num != self.num_quadro:
                    self.num_quadro = num
                    if self.ao_quadro:
                        self.ao_quadro(img)
            except Exception as e:
                log('quadro do WebView:', e)
                time.sleep(1)
            time.sleep(0.08)

    def ajustar_zoom(self, url, esperar=False):
        if QUADROS:
            return
        z = zoom_para(url)
        if z != self.zoom:
            self.zoom = z
            self.cmd('Emulation.setDeviceMetricsOverride', esperar=esperar, width=round(LARG / z), height=round(ALT / z),
                     deviceScaleFactor=z, mobile=True)

    def _ler(self):
        while True:
            m = json.loads(self.ws.recv())
            if 'id' in m:
                ev = self.respostas.pop(m['id'], None)
                if ev:
                    ev[1] = m
                    ev[0].set()
            elif m.get('method') == 'Page.frameNavigated' and not m['params']['frame'].get('parentId'):
                self.url = m['params']['frame'].get('url', '')
                self.ajustar_zoom(self.url)   # aqui é a thread de leitura: não pode esperar resposta
            elif m.get('method') == 'Page.screencastFrame':
                p = m['params']
                self.cmd('Page.screencastFrameAck', esperar=False, sessionId=p['sessionId'])
                if self.ao_quadro:
                    self.ao_quadro(Image.open(BytesIO(b64decode(p['data']))).convert('RGB'))

    def cmd(self, metodo, esperar=True, **params):
        with self.trava:
            self.n += 1
            i = self.n
            ev = [threading.Event(), None]
            if esperar:
                self.respostas[i] = ev
            self.ws.send(json.dumps({'id': i, 'method': metodo, 'params': params}))
        if esperar:
            ev[0].wait(15)
            return (ev[1] or {}).get('result', {})

    def js(self, expr):
        r = self.cmd('Runtime.evaluate', expression=expr, returnByValue=True)
        return (r.get('result') or {}).get('value')

    def foto(self):
        if QUADROS:
            return self._quadro_webview()[1]
        r = self.cmd('Page.captureScreenshot', format='png')
        return Image.open(BytesIO(b64decode(r['data']))).convert('RGB') if r.get('data') else None


# ---------------- teclado virtual ----------------
LINHAS = ['1234567890', 'qwertyuiop', 'asdfghjkl@', 'zxcvbnm.,-']
ESPECIAIS = [('⇧', 'shift', 1), ('espaço', ' ', 3), ('⌫', 'apagar', 2), ('↵ OK', 'enter', 2), ('✕', 'fechar', 2)]
TECLA_A, TOPO_TECLADO = 36, ALT - 5 * 36 - 8


def teclas():
    """Lista (x0, y0, x1, y1, rótulo, ação)."""
    out = []
    for r, linha in enumerate(LINHAS):
        for c, ch in enumerate(linha):
            x0 = c * LARG // 10
            out.append((x0 + 2, TOPO_TECLADO + 4 + r * TECLA_A, (c + 1) * LARG // 10 - 2,
                        TOPO_TECLADO + 4 + (r + 1) * TECLA_A - 3, ch, ch))
    x = 0
    for rot, acao, peso in ESPECIAIS:
        w = LARG * peso // 10
        out.append((x + 2, TOPO_TECLADO + 4 + 4 * TECLA_A, x + w - 2, TOPO_TECLADO + 4 + 5 * TECLA_A - 3, rot, acao))
        x += w
    return out


TECLAS = teclas()


def tecla_em(cx, cy):
    return next((t for t in TECLAS if t[0] <= cx <= t[2] and t[1] <= cy <= t[3]), None)


def desenhar_teclado(img, maiusc, sob_cursor):
    d = ImageDraw.Draw(img)
    d.rectangle((0, TOPO_TECLADO, LARG, ALT), fill=(22, 27, 34))
    for t in TECLAS:
        rot = t[4].upper() if maiusc and len(t[4]) == 1 else t[4]
        ativo = (t[5] == 'shift' and maiusc)
        cor = (47, 129, 247) if t is sob_cursor else ((35, 134, 54) if ativo else (48, 54, 61))
        d.rounded_rectangle(t[:4], 6, fill=cor)
        f = FONTE if len(rot) <= 2 else FONTE_P
        w = d.textlength(rot, font=f)
        d.text(((t[0] + t[2] - w) / 2, (t[1] + t[3]) / 2), rot, font=f, fill=(230, 237, 243), anchor='lm')


# ---------------- sessão com o PS2 ----------------
class Sessao:
    def __init__(self, nav):
        self.nav = nav
        self.pagina = None          # último quadro da página
        self.enviado = None         # última imagem enviada ao PS2
        self.seq = 0
        self.ult_entrada = 0
        self.n_teclas = None
        self.pedido = None
        self.fila = []
        self.resultados = {}
        self.ra_copiado = False
        self.video_pid = None
        self.video_pos = 0
        self.botoes_video = 0
        self.pedido_n = int(time.time()) & 0xFFFFFF
        self.trava = threading.Lock()
        self.teclado = False
        self.maiusc = False
        self.sob = None
        self.botoes = 0
        self.cx = self.cy = 0
        self.ult_mov = 0
        nav.ao_quadro = self.novo_quadro

    # ---- tela ----
    def novo_quadro(self, img):
        if img.size != (LARG, ALT):
            img = img.resize((LARG, ALT))
        self.pagina = img
        self.enviar_tela()

    def enviar_tela(self, tudo=False):
        """Grava a tela para o PS2 ler pelo host: (dif.bin = mudanças desde a seq anterior, completa.bin = tudo)."""
        with self.trava:
            if self.pagina is None:
                return
            img = self.pagina.copy()
            if self.teclado:
                desenhar_teclado(img, self.maiusc, self.sob)
            ant = None if tudo else self.enviado
            if ant is not None and ImageChops.difference(img, ant).getbbox() is None:
                return
            regs, todos = [], []
            for y in range(0, ALT, FAIXA):
                faixa = img.crop((0, y, LARG, y + FAIXA))
                todos.append(registro(faixa, 0, y, LARG))
                if ant is not None:
                    caixa = ImageChops.difference(faixa, ant.crop((0, y, LARG, y + FAIXA))).getbbox()
                    if caixa:
                        regs.append(registro(faixa.crop((caixa[0], 0, caixa[2], FAIXA)), caixa[0], y, caixa[2] - caixa[0]))
            self.seq += 1
            cmd = self.cmd_atual()
            gravar(os.path.join(PASTA_PS2, 'completa.bin'), cabecalho(self.seq, 0, cmd, todos) + b''.join(todos))
            if ant is None:
                regs = todos
            gravar(os.path.join(PASTA_PS2, 'dif.bin'), cabecalho(self.seq, self.seq - 1, cmd, regs) + b''.join(regs))
            self.enviado = img

    # ---- controle ----
    def entrada(self, botoes, cx, cy, rx, ry):
        apertou = botoes & ~self.botoes
        self.botoes = botoes
        mudou_cursor = (cx, cy) != (self.cx, self.cy)
        self.cx, self.cy = cx, cy
        px, py = cx / self.nav.zoom, cy / self.nav.zoom
        no_teclado = self.teclado and cy >= TOPO_TECLADO
        n = self.nav

        if self.teclado:
            sob = tecla_em(cx, cy)
            if sob is not self.sob:
                self.sob = sob
                self.enviar_tela()
        if mudou_cursor and not no_teclado and time.time() - self.ult_mov > 0.03:
            self.ult_mov = time.time()
            n.cmd('Input.dispatchMouseEvent', esperar=False, type='mouseMoved', x=px, y=py)

        if apertou & B['X']:
            if no_teclado:
                self.digitar(tecla_em(cx, cy))
            else:
                for tipo in ('mousePressed', 'mouseReleased'):
                    n.cmd('Input.dispatchMouseEvent', type=tipo, x=px, y=py, button='left', clickCount=1)
                threading.Timer(0.35, self.ver_campo).start()
        if apertou & B['CIRCULO']:
            if self.teclado:
                self.mostrar_teclado(False)
            else:
                n.js('history.back()')
        if apertou & B['TRIANGULO']:
            n.cmd('Page.reload', esperar=False)
        if apertou & B['QUADRADO']:
            self.mostrar_teclado(not self.teclado)
        if apertou & B['START'] or apertou & B['L2']:
            n.cmd('Page.navigate', esperar=False, url=INICIO)
        if apertou & B['R2']:
            n.cmd('Page.navigate', esperar=False, url=LOJA)
        rolar = (-300 if apertou & B['L1'] else 0) + (300 if apertou & B['R1'] else 0) + ry * 0.5
        if rolar:
            n.cmd('Input.dispatchMouseEvent', esperar=False, type='mouseWheel', x=px, y=py, deltaX=0, deltaY=rolar)

    def mostrar_teclado(self, sim):
        self.teclado = sim
        self.sob = None
        if sim:   # deixa o campo focado visível acima do teclado
            self.nav.js("document.activeElement && document.activeElement.scrollIntoView && "
                        "document.activeElement.scrollIntoView({block:'start'})")
        self.enviar_tela()

    def ver_campo(self):
        tag = self.nav.js("(function(e){return e && (e.isContentEditable ? 'edit' : "
                          "(e.tagName + ':' + (e.type || '')))})(document.activeElement)") or ''
        texto = tag.startswith('TEXTAREA') or tag == 'edit' or (tag.startswith('INPUT:') and tag.split(':')[1] in (
            '', 'text', 'password', 'email', 'search', 'number', 'tel', 'url'))
        if texto != self.teclado:
            self.mostrar_teclado(texto)

    def digitar(self, t):
        if not t:
            return
        acao, n = t[5], self.nav
        if acao == 'shift':
            self.maiusc = not self.maiusc
            return self.enviar_tela()
        if acao == 'fechar':
            return self.mostrar_teclado(False)
        if acao == 'apagar':
            for tipo in ('rawKeyDown', 'keyUp'):
                n.cmd('Input.dispatchKeyEvent', type=tipo, key='Backspace', code='Backspace', windowsVirtualKeyCode=8)
            return
        if acao == 'enter':
            n.cmd('Input.dispatchKeyEvent', type='keyDown', key='Enter', code='Enter', windowsVirtualKeyCode=13, text='\r')
            n.cmd('Input.dispatchKeyEvent', type='keyUp', key='Enter', code='Enter', windowsVirtualKeyCode=13)
            return self.mostrar_teclado(False)
        n.cmd('Input.insertText', text=acao.upper() if self.maiusc else acao)
        if self.maiusc:   # maiúscula vale para uma letra só
            self.maiusc = False
            self.enviar_tela()

    # ---- ligação com o PS2 (arquivos no host:) ----
    def cmd_atual(self):
        cmd = 0   # música da loja desligada (pedido do usuário 17/10/2026: pesava o cursor); era MUSICA na loja.html
        if self.pedido and self.pedido.get('estado') in (None, 'copiando'):
            cmd |= PEDIDO
        return cmd

    def copiar(self, arquivo):
        """ROM de ps2/snes → pendrive USB do PS2 (mass:/SNES/), junto com o RetroArch (1ª vez na sessão)."""
        nome = os.path.basename(arquivo)
        if not os.path.isfile(os.path.join(PASTA_PS2, 'snes', nome)):
            return 'ROM não encontrada'
        if not self.aberto():
            return 'o navegador não está aberto no PS2'
        if not self.ra_copiado:
            self.enfileirar(0, f'host:snesticle/{RA_ELF}', f'{RA_PASTA}/{RA_ELF}', nome, 'instalando o emulador')
            self.enfileirar(0, 'host:snesticle/title.cfg', f'{RA_PASTA}/title.cfg', nome, 'instalando o emulador')
        self.enfileirar(0, f'host:snes/{nome}', f'mass:/SNES/{nome}', nome, 'copiando')
        return 'ok'

    def instalar_ra(self):
        """Só o RetroArch (passo 1 da loja): APPS/RETROARCH no pendrive do PS2."""
        if not self.aberto():
            return 'o navegador não está aberto no PS2'
        self.enfileirar(0, f'host:snesticle/{RA_ELF}', f'{RA_PASTA}/{RA_ELF}', '__retroarch__', 'instalando o emulador')
        self.enfileirar(0, 'host:snesticle/title.cfg', f'{RA_PASTA}/title.cfg', '__retroarch__', 'instalando o emulador')
        return 'ok'

    def jogar(self, arquivo):
        """Abre o RetroArch do pendrive com a ROM do pendrive (o navegador fecha e o PS2 roda o RetroArch)."""
        nome = os.path.basename(arquivo)
        if not self.aberto():
            return 'o navegador não está aberto no PS2'
        self.enfileirar(1, f'{RA_PASTA}/{RA_ELF}', f'mass:/SNES/{nome}', nome, 'abrindo')
        return 'ok'

    def neutrino(self, iso):
        """Jogo de PS2 pela rede (TV box, 17/10/2026): o Neutrino lê o ISO no servidor udpfs da box (udpfs_nuvem.py:
        pendrive da box ou, se não estiver lá, o HD do notebook por HTTPS). O Neutrino abre pelo host: (navlink,
        ps2/neutrino/ servido por esta box), como pelo PS2Link: o elf-loader não reinicia o IOP, então ele ainda lê
        config/ e modules/ por aqui antes de montar o ambiente do jogo. Do pendrive (mass:) ele falhava antes da rede."""
        nome = os.path.basename(iso)
        if not self.aberto():
            return 'o navegador não está aberto no PS2'
        args = f'-bsd=udpfs|-dvd=udpfs:DVD/{nome}'
        # DualShock 3/4 por Bluetooth no jogo (18/10/2026): PadEmu do OPL via config/pademu.toml, se existir (apagar o
        # arquivo desliga); o pedido para o PS2 tem no máximo 127 bytes, então ISO de nome longo vai sem ele
        if os.path.exists(os.path.join(PASTA_PS2, 'neutrino', 'config', 'pademu.toml')) and len(args) + 12 <= 127:
            args += '|-cfg=pademu'
        self.enfileirar(1, 'host:neutrino/neutrino.elf', args, '__neutrino__', 'abrindo')
        return 'ok'

    def enfileirar(self, op, origem, destino, rotulo, fase):
        o, d = origem.encode(), destino.encode()
        if len(o) > 127 or len(d) > 127:
            return
        self.pedido_n += 1
        try:   # host:video/remoto/... não existe aqui (vem do notebook pelo servidor_host.py)
            tam = os.path.getsize(os.path.join(PASTA_PS2, origem[5:])) if origem.startswith('host:') else 0
        except OSError:
            tam = 0
        self.fila.append({'id': self.pedido_n, 'op': op, 'origem': o, 'destino': d, 'tamanho': tam,
                          'arquivo': rotulo, 'fase': fase, 'estado': None, 'pct': 0, 't': time.time()})
        if not self.pedido:
            self.proximo_pedido()

    def proximo_pedido(self):
        self.pedido = self.fila.pop(0) if self.fila else None
        if not self.pedido:
            # fila vazia: tira o pedido entregue, senão um navegador aberto depois (outra sessão) o faria de novo
            try:
                os.remove(os.path.join(PASTA_PS2, 'pedido.bin'))
            except OSError:
                pass
            return
        p = self.pedido
        gravar(os.path.join(PASTA_PS2, 'pedido.bin'), b'PSP1' + struct.pack('<II', p['id'], p['tamanho'])
               + p['origem'].ljust(128, b'\0') + p['destino'].ljust(128, b'\0') + struct.pack('<I', p['op']))
        with self.trava:   # avisa já (sem esperar mudança de tela): cabeçalho com a mesma seq e o bit de pedido
            gravar(os.path.join(PASTA_PS2, 'dif.bin'), cabecalho(self.seq, self.seq, self.cmd_atual(), []))
        log('pedido ao PS2:', p['fase'], p['destino'].decode())

    def video(self, sessao):
        """Cinema: manda o PS2 tocar host:video/<sessão>.m2v + .pcm (op 2)."""
        if not self.aberto():
            return 'o navegador não está aberto no PS2'
        self.enfileirar(2, f'host:video/{sessao}.m2v', f'host:video/{sessao}.pcm', '__video__', 'tocando')
        self.video_pid = self.pedido_n
        return 'ok'

    def avisar_cinema(self, acao, **dados):
        if not CINEMA:
            return
        try:
            req = urllib.request.Request(CINEMA + acao, data=json.dumps(dados).encode(), method='POST',
                                         headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:
            log('cinema', acao, e)

    def estado_pedidos(self):
        """Para a loja: o pedido em andamento e o último resultado de cada ROM."""
        atual = None
        if self.pedido:
            atual = {k: v for k, v in self.pedido.items() if k not in ('origem', 'destino')}
        return {'atual': atual, 'resultados': self.resultados, 'na_fila': len(self.fila)}

    def aberto(self):
        """O PS2 escreve entrada.bin enquanto o navegador roda. No real (17/10/2026) o intervalo foi de 7 a 11 s
        com a tela parada, e com 6 s de limite a loja desativava o botão do RetroArch; 20 s cobre isso."""
        return time.time() - self.ult_entrada < 20

    def vigiar_entrada(self):
        arq = os.path.join(PASTA_PS2, 'entrada.bin')
        try:   # arquivo de uma sessão antiga não conta como "PS2 aberto"
            st = os.stat(arq)
            visto = (st.st_mtime_ns, st.st_size)
        except OSError:
            visto = None
        while True:
            time.sleep(0.02)
            try:
                st = os.stat(arq)
                if (st.st_mtime_ns, st.st_size) == visto:
                    continue
                visto = (st.st_mtime_ns, st.st_size)
                d = open(arq, 'rb').read()
            except OSError:
                continue
            if len(d) < 84 or d[:4] != b'PSI2':
                continue
            if not self.aberto():
                log('PS2 conectado (navegador aberto)')
                # sessão nova do navegador: um "abrir ELF/jogo" (op 1) ou vídeo (op 2) já foi entregue à sessão
                # anterior — se ficasse no pedido.bin, o navegador recém-aberto abria o jogo de novo sozinho (18/10/2026)
                if self.pedido and self.pedido['op'] in (1, 2):
                    log('pedido antigo descartado:', self.pedido['fase'], self.pedido['destino'].decode())
                    self.pedido = None
                    try:
                        os.remove(os.path.join(PASTA_PS2, 'pedido.bin'))
                    except OSError:
                        pass
                    self.proximo_pedido()
                self.n_teclas = None
                self.ra_copiado = False   # pode ser outro pendrive
                threading.Thread(target=self.enviar_tela, args=(True,), daemon=True).start()
            self.ult_entrada = time.time()
            botoes, cx, cy, rx, ry, seq, n_teclas, roda = struct.unpack('<HHHbbIHb', d[4:19])
            if len(d) >= 96:   # modo vídeo: posição e fim
                ativo, pos_ms = d[91], struct.unpack('<i', d[92:96])[0]
                pid, est = struct.unpack('<IB', d[84:89])
                if ativo:
                    self.video_pos = pos_ms / 1000
                    apertou = botoes & ~self.botoes_video
                    if apertou & (B['LEFT'] | B['RIGHT']):
                        seg = 30 if apertou & B['RIGHT'] else -30
                        threading.Thread(target=self.avisar_cinema, args=('pular',),
                                         kwargs={'seg': seg, 'pos': self.video_pos}, daemon=True).start()
                    self.botoes_video = botoes
                if pid == getattr(self, 'video_pid', None) and est in (9, 10):
                    self.video_pid = None
                    threading.Thread(target=self.avisar_cinema, args=('parado',), kwargs={'pos': self.video_pos},
                                     daemon=True).start()
            if len(d) >= 92 and self.pedido:
                pid, est, pct, usb = struct.unpack('<IBBB', d[84:91])
                if pid == self.pedido['id'] and est:
                    novo = ESTADOS_PEDIDO.get(est, f'estado {est}')
                    if novo != self.pedido['estado']:
                        log('pedido', self.pedido['destino'].decode(), '→', novo, f'(driver USB: {usb})')
                    self.pedido.update(estado=novo, pct=pct, usb=usb)
                    if est >= 2:   # terminou: guarda o resultado e segue a fila
                        p = self.pedido
                        if p['op'] == 0 and p['destino'].endswith(RA_ELF.encode()):
                            self.ra_copiado = est == 2
                            self.resultados['__retroarch__'] = {'op': 0, 'estado': novo, 'ok': est == 2, 't': time.time(),
                                                                'no_pendrive': est == 2}
                        falhou = est not in (2, 7, 8)
                        if falhou or p['fase'] in ('copiando', 'abrindo', 'apagando'):
                            antes = self.resultados.get(p['arquivo'], {})
                            self.resultados[p['arquivo']] = {'op': p['op'], 'estado': novo, 'ok': not falhou, 't': time.time(),
                                                            'no_pendrive': antes.get('no_pendrive') or (p['op'] == 0 and not falhou)
                                                            or (p['op'] == 1 and not falhou)}
                        if falhou:   # não adianta seguir (ex.: sem pendrive)
                            self.fila = [x for x in self.fila if x['arquivo'] != p['arquivo']]
                        self.proximo_pedido()
            if len(d) >= 96 and d[91]:   # vídeo tocando: o controle é do player, não da página
                self.botoes = botoes
                continue
            try:
                self.teclas_usb(n_teclas, d[20:84])
                self.entrada(botoes, cx, cy, rx, ry + roda * 2)
            except Exception as e:
                log('controle:', e)

    def teclas_usb(self, n, anel):
        """Teclado USB do PS2: aplica as teclas novas desde a última leitura (anel de 64)."""
        if self.n_teclas is None or n < self.n_teclas or n - self.n_teclas > 64:
            self.n_teclas = n   # sessão nova: não repete teclas antigas
            return
        for k in range(self.n_teclas, n):
            c = anel[k % 64]
            self.tecla(c)
        self.n_teclas = n

    def tecla(self, c):
        n = self.nav
        def apertar(key, code, vk, texto=None):
            extra = {'text': texto} if texto else {}
            n.cmd('Input.dispatchKeyEvent', type='keyDown' if texto else 'rawKeyDown', key=key, code=code,
                  windowsVirtualKeyCode=vk, **extra)
            n.cmd('Input.dispatchKeyEvent', type='keyUp', key=key, code=code, windowsVirtualKeyCode=vk)
        if c in (8, 127):
            apertar('Backspace', 'Backspace', 8)
        elif c in (10, 13):
            apertar('Enter', 'Enter', 13, '\r')
            if self.teclado:
                self.mostrar_teclado(False)
        elif c == 9:
            apertar('Tab', 'Tab', 9)
        elif c & 0x80:
            esp = ESPECIAIS_USB.get(c & 0x7F)
            if esp:
                apertar(*esp)
            else:
                log('tecla especial desconhecida do teclado USB:', hex(c & 0x7F))
        elif c >= 32:
            n.cmd('Input.insertText', text=chr(c))

    def sair(self):
        """Manda o PS2 fechar o navegador (ele volta ao PS2Link): dif.bin com cmd 1."""
        if not self.aberto():
            return False
        with self.trava:
            gravar(os.path.join(PASTA_PS2, 'dif.bin'), cabecalho(self.seq, self.seq, 1, []))
        self.ult_entrada = 0
        threading.Timer(15, self.enviar_tela, args=(True,)).start()   # tira o "sair" para a próxima sessão
        return True


def registro(img, x, y, w):
    dados = zlib.compress(img.tobytes('raw', 'RGBX'), 1)
    return b'PSF2' + struct.pack('<HHHHII', x, y, w, FAIXA, len(dados), zlib.crc32(dados)) + dados


def cabecalho(seq, base, cmd, regs):
    return b'PST2' + struct.pack('<IIII', seq, base, cmd, sum(map(len, regs)))


def gravar(caminho, dados):
    tmp = caminho + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(dados)
    os.replace(tmp, caminho)


def controle(sessao):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((os.environ.get('PS2_NAV_CONTROLE_IP', '127.0.0.1'), PORTA_CONTROLE))   # TV box: 0.0.0.0 (o notebook manda)
    srv.listen(4)
    while True:
        c, _ = srv.accept()
        with c:
            pedido = c.recv(1024).decode('utf-8', errors='ignore').strip()
            if pedido == 'sair':
                c.sendall(b'ok\n' if sessao.sair() else b'fechado\n')
            elif pedido.startswith('copiar '):
                c.sendall((sessao.copiar(pedido[7:]) + '\n').encode())
            elif pedido == 'retroarch':
                c.sendall((sessao.instalar_ra() + '\n').encode())
            elif pedido.startswith('copiar2 ') or pedido.startswith('apagar '):   # cinema: arquivo ↔ pendrive do PS2
                partes = pedido.split(' ', 1)[1].split('|')
                if not sessao.aberto():
                    c.sendall(b'o navegador nao esta aberto no PS2\n')
                elif partes[0] == 'copiar2' or pedido.startswith('copiar2'):
                    origem, destino, rotulo = partes
                    sessao.enfileirar(0, origem, destino, rotulo, 'copiando')
                    c.sendall(b'ok\n')
                else:
                    destino, rotulo = partes
                    sessao.enfileirar(3, destino, '', rotulo, 'apagando')
                    c.sendall(b'ok\n')
            elif pedido.startswith('video '):
                c.sendall((sessao.video(pedido[6:].strip()) + '\n').encode())
            elif pedido.startswith('neutrino '):
                c.sendall((sessao.neutrino(pedido[9:].strip()) + '\n').encode())
            elif pedido.startswith('jogar '):
                c.sendall((sessao.jogar(pedido[6:]) + '\n').encode())
            elif pedido == 'pedido':
                c.sendall((json.dumps(sessao.estado_pedidos()) + '\n').encode())
            elif pedido in ('loja', 'sistema', 'cinema'):   # muda a página (vale também antes de abrir no PS2)
                sessao.nav.cmd('Page.navigate', esperar=False, url={'loja': LOJA, 'cinema': CINEMA_PAG}.get(pedido, INICIO))
                c.sendall(b'ok\n')
            else:
                c.sendall(b'aberto\n' if sessao.aberto() else b'fechado\n')


def main():
    nav = Chromium()
    sessao = Sessao(nav)
    threading.Thread(target=controle, args=(sessao,), daemon=True).start()
    threading.Thread(target=sessao.vigiar_entrada, daemon=True).start()
    sessao.pagina = nav.foto()
    sessao.enviar_tela(True)
    log(f'navegador do PS2 pronto (arquivos em {PASTA_PS2}), página inicial {INICIO}')
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
