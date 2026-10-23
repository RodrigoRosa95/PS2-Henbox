#!/usr/bin/env python3
"""Vídeo tutorial do PS2 Henbox (23/10/2026): telas reais + cartões + narração Piper pt-BR + legendas → MP4 1280x720.
Uso: ~/xoom-assistente/venv/bin/python montar_video.py SAIDA.mp4"""
import os, subprocess, sys, wave
from PIL import Image, ImageDraw, ImageFont, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
OBRA = os.path.join(AQUI, 'obra')
os.makedirs(OBRA, exist_ok=True)
R = os.path.expanduser('~/ps2-navegador-github/docs/telas/')
A = R + 'automacao/'
I = os.path.expanduser('~/Imagens/')
ARQ = os.path.expanduser('~/ps2-navegador-github/docs/arquitetura.png')
W, H = 1280, 720
FONTE = '/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf'
AZUL, FUNDO, AMARELO, CINZA = '#2f81f7', '#0b1630', '#ffd166', '#9fb4e0'


def f(tam, negrito=False):
    return ImageFont.truetype(FONTE % ('-Bold' if negrito else ''), tam)


# Cada cena: (imagem ou cartão, título, [frases narradas]). Cartão = ('cartao', [linhas]).
CENAS = [
    (('cartao', ['PS2 Henbox', 'o "HEN" do PlayStation 2', '', 'Apresentação e instalação do zero']), None, [
        'Olá! Este é o PS2 Henbox, um projeto que dá ao PlayStation 2 uma interface nova, com loja, jogos pela rede, '
        'vídeos e até conquistas do RetroAchievements.',
        'Tudo isso sem modchip e sem abrir o console.']),
    (ARQ, 'Como funciona', [
        'A ideia é simples: o PS2 vira um cliente leve, e uma TV box Android barata vira o cérebro do sistema.',
        'A TV box desenha as telas, guarda e serve os jogos, e manda a imagem pronta para o PS2 pela rede.']),
    (R + '1-menu.png', 'O menu no PS2', [
        'Este é o menu que aparece na sua TV, direto no PS2.',
        'Você navega com o controle normal do PlayStation.']),
    (R + '2-loja.png', 'Loja', [
        'Na loja ficam os jogos da sua coleção, com capa e informações.',
        'Use sempre cópias dos seus próprios jogos.']),
    (R + '3-jogar-pela-rede.png', 'Jogar pela rede', [
        'Com um toque, o jogo abre pela rede, lido direto da TV box ou do seu servidor, sem copiar nada para o PS2.']),
    (R + '4-videos.png', 'Vídeos', [
        'Também dá para assistir vídeos no próprio PS2.']),
    (('cartao', ['Do que você precisa', '', '• PS2 com rede (Fat com adaptador ou Slim)', '• OPL no memory card (FreeMcBoot)',
                 '• TV box Android com root e porta de rede', '• Um pendrive e um celular Android']), None, [
        'Para instalar, você precisa de: um PS2 com rede, o Open PS2 Loader no memory card, uma TV box Android com root, '
        'um pendrive e um celular.']),
    (A + 'app-1-inicio.png', 'Passo 1 · App PS2 Henbox', [
        'Passo um: instale o app PS2 Henbox no celular. O link está no GitHub do projeto.',
        'No app, toque em procurar TV boxes, escolha a sua e toque em instalar e atualizar tudo.',
        'O app instala tudo sozinho na TV box, até o Python, sem depender da internet da box.']),
    (A + 'app-3-pendrive-e-conquistas.png', 'Passo 2 · Pendrive do PS2', [
        'Passo dois: espete um pendrive na USB da TV box e toque em preparar pendrive.',
        'A box copia o PS2 Henbox com o endereço de rede certo. Não precisa de computador.',
        'Depois, é só colocar o pendrive na USB da frente do PS2.']),
    (('cartao', ['Passo 3 · Cabo de rede', '', 'PS2  ⇄  cabo  ⇄  TV box  ⇄  Wi-Fi  ⇄  internet', '',
                 'A box percebe o PS2 sozinha e leva ele', 'para a internet pelo Wi-Fi dela.']), None, [
        'Passo três: ligue o cabo de rede do PS2 direto na TV box.',
        'A box percebe o PS2 sozinha e leva ele para a internet pelo Wi-Fi, em qualquer casa, sem configurar nada.']),
    (('cartao', ['Passo 4 · Abrir no PS2', '', 'OPL  →  Apps  →  PS2 Henbox']), None, [
        'Passo quatro: no PS2, abra o OPL, vá em Apps e escolha PS2 Henbox.',
        'Em poucos segundos a TV box encontra o PS2 e o menu aparece na tela.']),
    (A + 'app-2-estado-completo.png', 'Estado completo', [
        'Se algo não funcionar, toque em estado completo no app.',
        'Cada parte aparece com um sinal verde ou vermelho, e o que fazer para resolver.']),
    (A + 'pagina-estado-ps2.png', 'Estado na tela do PS2', [
        'A mesma conferência também aparece na própria tela do PS2.']),
    (I + 'conquistas-ps2-inicio.png', 'Conquistas RetroAchievements', [
        'Agora, as conquistas. Com o app xeRAbora na TV box, os jogos ganham conquistas do RetroAchievements no PS2 de verdade.',
        'A TV box prepara tudo sozinha para cada jogo novo.']),
    (I + 'conquistas-ps2-black.png', 'Progresso do jogo', [
        'Você acompanha o progresso e as medalhas de cada jogo.']),
    (A + 'app-5-conquistas.png', 'Conquistas no app', [
        'No app do celular, a aba de conquistas mostra o que você desbloqueou, em tempo real.']),
    (I + 'ps2-conquistas-app-3-notificacao.png', 'Aviso no celular', [
        'E a cada conquista chega uma notificação com a medalha e um plim de troféu.']),
    (A + 'app-6-opcao-voz.png', 'Voz opcional', [
        'Se quiser, depois do plim uma voz avisa.', '#VOZ#']),
    (A + 'xoom-show-trofeu.png', 'Também no tablet', [
        'O aviso também aparece em um tablet na parede, como um pop-up de troféu.']),
    (A + 'servidor-qr-pareamento.png', 'Opcional · Servidor em nuvem', [
        'Opcional: com um computador, você pode criar o seu servidor com a sua coleção.',
        'Ele mostra um QR code. Aponte a câmera do celular e o app conecta o servidor na TV box.']),
    (('cartao', ['Atualização automática', '', 'A TV box se atualiza sozinha', 'e atualiza o pendrive do PS2', 'na próxima conexão.']), None, [
        'E não precisa se preocupar com atualizações: a TV box se atualiza sozinha, e atualiza o pendrive do PS2 na próxima vez.']),
    (('cartao', ['Quer testar?', '', 'github.com/RodrigoRosa95/PS2-Henbox', '',
                 'WhatsApp: +55 51 99994-7239', 'digorpassos16245@gmail.com']), None, [
        'Gostou? O projeto, os arquivos e o passo a passo estão no GitHub.',
        'Dúvidas ou sugestões, me chame no WhatsApp ou por e-mail. Até a próxima!']),
]

FRASE_VOZ = 'Você desbloqueou uma conquista no Play 2.'


def cartao(linhas):
    img = Image.new('RGB', (W, H), FUNDO)
    d = ImageDraw.Draw(img)
    for y in range(H):   # degradê leve
        d.line([(0, y), (W, y)], fill=(11, 22 + y // 24, 48 + y // 12))
    y = 150 if len(linhas) > 3 else 230
    for k, l in enumerate(linhas):
        fn = f(64, True) if k == 0 else f(34)
        cor = 'white' if k == 0 else (AMARELO if l.startswith(('OPL', 'PS2 ', 'github', 'WhatsApp')) else CINZA)
        if l:
            w = d.textlength(l, font=fn)
            d.text(((W - w) / 2, y), l, font=fn, fill=cor)
        y += 80 if k == 0 else 50
    return img


def tela(caminho, titulo):
    src = Image.open(caminho).convert('RGB')
    fundo = src.resize((W, H)).filter(ImageFilter.GaussianBlur(28))
    fundo = Image.blend(fundo, Image.new('RGB', (W, H), FUNDO), 0.65)
    caixa_w, caixa_h = W - 120, H - 230
    esc = min(caixa_w / src.width, caixa_h / src.height)
    nova = src.resize((int(src.width * esc), int(src.height * esc)), Image.LANCZOS)
    x, y = (W - nova.width) // 2, 80 + (caixa_h - nova.height) // 2
    d = ImageDraw.Draw(fundo)
    d.rounded_rectangle([x - 6, y - 6, x + nova.width + 6, y + nova.height + 6], 14, fill='#1d3b78')
    fundo.paste(nova, (x, y))
    d.text((40, 22), titulo, font=f(36, True), fill='white')
    return fundo


def legenda(img, texto):
    img = img.copy()
    d = ImageDraw.Draw(img, 'RGBA')
    fn = f(28)
    palavras, linhas, atual = texto.split(), [], ''
    for p in palavras:
        t = (atual + ' ' + p).strip()
        if d.textlength(t, font=fn) > W - 140:
            linhas.append(atual)
            atual = p
        else:
            atual = t
    linhas.append(atual)
    alto = 40 * len(linhas) + 24
    y0 = H - alto - 18
    d.rounded_rectangle([50, y0, W - 50, H - 18], 14, fill=(0, 0, 0, 185))
    for k, l in enumerate(linhas):
        w = d.textlength(l, font=fn)
        d.text(((W - w) / 2, y0 + 12 + 40 * k), l, font=fn, fill='white')
    return img


def narrar(texto, destino, voz):
    with wave.open(destino, 'wb') as w:
        voz.synthesize_wav(texto, w)
    with wave.open(destino) as w:
        return w.getnframes() / w.getframerate()


def main():
    saida = sys.argv[1]
    sys.path.insert(0, os.path.expanduser('~/xoom-assistente'))
    from piper import PiperVoice
    voz = PiperVoice.load(os.path.expanduser('~/xoom-assistente/modelos/pt_BR-faber-medium.onnx'))
    plim = os.path.expanduser('~/ps2-monitor/navegador/sons/trofeu.wav')
    partes, n = [], 0
    for fonte, titulo, frases in CENAS:
        base = cartao(fonte[1]) if isinstance(fonte, tuple) else tela(fonte, titulo)
        for frase in frases:
            n += 1
            png, wav, mp4 = (os.path.join(OBRA, f'{n:03d}.{e}') for e in ('png', 'wav', 'mp4'))
            if frase == '#VOZ#':   # demonstração: plim + a frase do troféu
                dur_v = narrar(FRASE_VOZ, wav + '.voz.wav', voz)
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', plim, '-i', wav + '.voz.wav', '-filter_complex',
                                '[0:a]aresample=22050,aformat=channel_layouts=mono[a0];[1:a]aresample=22050,aformat=channel_layouts=mono,adelay=1100[a1];'
                                '[a0][a1]amix=inputs=2:duration=longest:normalize=0', wav], check=True)
                dur = dur_v + 1.1
                legenda(base, '(plim)  "' + FRASE_VOZ + '"').save(png)
            else:
                dur = narrar(frase, wav, voz)
                legenda(base, frase).save(png)
            total = dur + 0.6
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-i', png, '-i', wav,
                            '-af', 'apad', '-t', f'{total:.2f}', '-r', '25', '-c:v', 'libx264', '-tune', 'stillimage',
                            '-preset', 'veryfast', '-crf', '24', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k',
                            '-ar', '44100', '-ac', '1', mp4], check=True)
            partes.append(mp4)
            print(f'{n:03d} {total:5.1f}s {frase[:60]}', flush=True)
    lista = os.path.join(OBRA, 'lista.txt')
    open(lista, 'w').write(''.join(f"file '{p}'\n" for p in partes))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lista, '-c', 'copy',
                    '-movflags', '+faststart', saida], check=True)
    print('pronto:', saida)


if __name__ == '__main__':
    main()
