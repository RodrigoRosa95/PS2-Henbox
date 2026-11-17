# Integração na TV box (PS2 Henbox)

O módulo [`pes14.py`](pes14.py) é independente: ele só precisa de **quatro peças** que o Henbox já tem — um pedido ao
`navegador.elf` (`op`), saber se o navegador está aberto (`aberto`), um GET no notebook (`buscar`) e, opcionalmente, a
faixa de aviso da tela do PS2 (`progresso`). Os trechos abaixo ligam essas peças. Eles vêm de um `navegador_servidor.py`
e um `videos.py` que já têm a fila do memory card (`op_mc` / `mc_trabalho`, do backup dos cartões); se a sua versão
não tem, adapte `op_mc`: é um pedido por vez ao navegador, esperando o fim, que devolve `True` se deu certo.

1. Copie `pes14.py` para a pasta do navegador na box (junto de `navegador_servidor.py`).
2. Cole os trechos abaixo.
3. Reinicie **só** o `videos.py` e o `navegador_servidor.py` (reiniciar o `servidor_host.py` derruba o `host:` do PS2).

## `navegador_servidor.py`

**Import** (junto dos outros `import`):

```python
import pes14   # ⚽ save do PES 14 com as transferências atuais, vindo do notebook
```

**Métodos da sessão** (dentro da classe que tem `op_mc`, `mc_trabalho`, `aberto` e `avisar`):

```python
    def pes14_buscar(self, caminho):
        """GET no servidor do notebook (rede de casa), com a chave da box. Devolve os bytes."""
        c = json.load(open(os.path.join(PASTA, 'config.json'), encoding='utf-8')).get('notebook') or {}
        casa = (c.get('casa') or '').rstrip('/')
        if not casa:
            raise OSError('a box não sabe o endereço do notebook (config.json → notebook.casa)')
        req = urllib.request.Request(casa + caminho, headers={'User-Agent': 'henbox-pes14', 'X-Chave': c.get('chave', '')})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def pes14_atualizar(self, forcar=False, desfazer=False):
        """⚽ Baixa o save atualizado e grava no cartão, com backup e conferência (pes14.py). Numa thread própria, com o
        andamento (etapa, segundos e barra) na faixa da tela do PS2. Se o cartão estiver em uso (o backup automático
        roda ao abrir o navegador), espera a vez em vez de recusar. Devolve 'ok' ou o texto que a página mostra."""
        def fazer(_b):
            def progresso(texto, pct):
                self.avisar('PES 14: ' + texto[:28], girando=True, pct=pct)   # sem emoji: a fonte da faixa (DejaVu) não tem ⚽

            a = pes14.Atualizador(self.op_mc, PASTA_PS2, self.aberto, self.pes14_buscar, log, progresso=progresso)
            ok, msg = a.desfazer() if desfazer else a.rodar(forcar)
            # a faixa só cabe ~45 caracteres: o texto completo fica na página /pes14
            texto = '✔ ' + ('Save anterior devolvido' if desfazer else msg.split(' (')[0].split('.')[0]) if ok else '⚠ ' + msg[:42]
            self.avisar(texto, girando=False, cor=(63, 185, 80) if ok else (248, 81, 73), segundos=10)

        if self.mc_trabalho(fazer):
            return 'ok'
        if getattr(self, 'pes14_esperando', False):
            return 'Já está na fila: a atualização começa sozinha quando o cartão ficar livre.'
        self.pes14_esperando = True

        def esperar():
            try:
                self.avisar('PES 14: aguardando o cartão', girando=True)
                fim = time.time() + 900
                while time.time() < fim:
                    time.sleep(2)
                    if self.mc_trabalho(fazer):
                        return
                self.avisar('⚠ O cartão continua ocupado. Tente de novo', girando=False, cor=(248, 81, 73), segundos=8)
            finally:
                self.pes14_esperando = False

        threading.Thread(target=esperar, daemon=True).start()
        return 'Na fila: o backup do memory card está rodando; a atualização começa sozinha logo em seguida.'
```

**Comandos** (na lista de `elif pedido ...` do servidor de controle, porta 8772):

```python
    elif pedido in ('pes14-atualizar', 'pes14-atualizar forcar', 'pes14-desfazer'):   # ⚽ save do PES 14 (videos.py /pes14)
        if not sessao.aberto():
            c.sendall(b'o navegador nao esta aberto no PS2\n')
        else:
            c.sendall(sessao.pes14_atualizar(pedido.endswith('forcar'), pedido == 'pes14-desfazer').encode() + b'\n')
```

**Opcional — desligar o backup automático do memory card**, que usa a mesma fila (a atualização espera a vez, mas o backup
automático é demorado). Troque o `Timer(45, self.mc_rodar)` por:

```python
if not os.path.exists(os.path.join(PASTA_PS2, 'MCBACKUP-AUTO-DESLIGADO')):
    threading.Timer(45, self.mc_rodar).start()
```

## `videos.py` (página inicial da box)

**Funções da página** (antes de `pagina_mc_confirma`, ou em qualquer lugar do arquivo):

```python
# ---------- ⚽ Atualizar o save do PES 14 (pes14.py, 16/11/2026) ----------
def pes14_estado():
    try:
        return json.load(open(os.path.join(PASTA, 'ps2', 'pes14', 'estado.json'), encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def pes14_manifesto():
    """O que o notebook tem para baixar agora (manifest.json); None se ele não responde."""
    try:
        c = json.load(open(os.path.join(PASTA, 'config.json'), encoding='utf-8')).get('notebook') or {}
        req = urllib.request.Request(c['casa'].rstrip('/') + '/pes14/manifest.json',
                                     headers={'User-Agent': 'henbox-pes14', 'X-Chave': c.get('chave', '')})
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def pagina_pes14(msg=''):
    e, m = pes14_estado(), pes14_manifesto()
    r, fase = e.get('resultado') or {}, e.get('fase')
    if m:
        res = m.get('resumo') or {}
        dispo = (f'No notebook: versão {html.escape(m["versao"])} (gerada em {html.escape(m.get("gerado", ""))}) com '
                 f'{res.get("transferencias", "?")} transferências.')
        if e.get('versao') == m['versao']:
            dispo += ' Seu save já está nessa versão.'
        exemplos = ''.join(f'<div class="p">• {html.escape(x)}</div>' for x in (res.get('exemplos') or [])[:8])
    else:
        dispo, exemplos = '⚠ O notebook não respondeu: não dá para baixar agora.', ''
    estado_msg = msg or (f'{fase}… {e.get("pct", 0)}%' if fase else r.get('msg')) or ''   # durante o trabalho: etapa e %
    volta = '<meta http-equiv="refresh" content="3;url=/pes14">' if fase else ''
    atual = (f'Instalada: versão {html.escape(e["versao"])} no {html.escape(e.get("cartao", ""))}.'
             if e.get('versao') else 'Ainda não atualizado por aqui.')
    botoes = '' if fase else (
        '<a class="b" href="/pes14/agora">⚽ Atualizar agora</a>'
        + (f'<a class="b" href="/pes14/desfazer">↩ Desfazer (voltar o save anterior)'
           f'<div class="p">backup de {html.escape(e["backup"])}</div></a>' if e.get('backup') else ''))
    return (f'{volta}<h1>⚽ PES 14: transferências</h1>'
            + (f'<div class="msg">{html.escape(estado_msg)}</div>' if estado_msg else '')
            + f'<div class="lista"><a class="b" href="/">← Voltar</a>{botoes}'
              f'<div class="p">{dispo}<br>{atual}</div>{exemplos}'
              '<div class="p" style="margin-top:8px">Antes de gravar, o save atual é guardado na box e o que foi gravado '
              'é lido de volta e conferido; se falhar, o anterior volta sozinho. Só o Option File é trocado: edições '
              'suas nele (uniformes, times editados) serão substituídas.</div></div>')
```

**Rotas** (na cadeia de `elif u.path == ...` do `do_GET`):

```python
        elif u.path in ('/pes14', '/pes14/agora', '/pes14/desfazer'):
            if u.path == '/pes14':
                self.pagina(pagina_pes14())
            elif not q.get('ok'):
                desf = u.path.endswith('desfazer')
                self.pagina(f'<h1>{"↩ Voltar o save anterior?" if desf else "⚽ Atualizar o save do PES 14?"}</h1>'
                            '<div class="msg">' + ('O Option File do cartão será trocado pelo do último backup.' if desf else
                            'O Option File do PES 14 no cartão será trocado pelo atualizado. O atual fica guardado na box.')
                            + '</div><div class="lista">'
                            f'<a class="b" href="{u.path}?ok=1">✔ Confirmar</a><a class="b" href="/pes14">← Voltar</a></div>')
            else:
                r = navegador('pes14-desfazer' if u.path.endswith('desfazer') else 'pes14-atualizar')
                self.pagina(pagina_pes14('Pedido iniciado: acompanhe abaixo.' if r == 'ok' else r))
```

**Botão na tela inicial** (ao lado dos outros `class="b grande"`):

```python
'<a class="b grande" href="/pes14">⚽ PES 14: transferências</a>'
```

## Notebook (servidor HTTP)

O `pes14.py` baixa de `<notebook.casa>/pes14/manifest.json` e `<notebook.casa>/pes14/<pasta-do-save>/<arquivo>` com o
cabeçalho `X-Chave` do `config.json` da box. Sirva a pasta `publicado/` (veja `notebook/publicar.py`) em `/pes14/` por
qualquer servidor HTTP da rede de casa; no Henbox, o `servidor.py` já serve a pasta do projeto, então basta apontar
`PES14_PUBLICAR` para `<projeto>/pes14`.
