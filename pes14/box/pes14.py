#!/usr/bin/env python3
"""⚽ Atualizar o save do PES 2014 (Option File) com as transferências atuais (16/11/2026).

O notebook gera o save já atualizado (pes14/notebook) e o publica em /pes14/ no servidor HTTP da rede com um manifesto
(versão, tamanho e sha256 de cada arquivo). Aqui, pelo navegador.elf, um pedido por vez (op 0 copia, op 6 cria pasta,
op 8 lista), como o mc_backup.py:

  1. acha o save do PES no mc0 ou mc1 (sem save não faz nada: o jogo precisa ter criado o Option File antes);
  2. baixa os arquivos do notebook e confere o sha256;
  3. guarda o save atual em ps2/pes14/backup/<data>/ (confere o tamanho de cada cópia) — nada é gravado sem backup;
  4. grava só o(s) arquivo(s) novo(s) por cima, lê de volta e compara; se algo falhar, volta o backup.

Os arquivos de ícone do save não mudam: só o Option File é regravado. O estado vai em ps2/pes14/estado.json.
"""
import contextlib, hashlib, json, math, os, shutil, threading, time, urllib.request

PASTA_SAVE_PADRAO = 'BESLES-556762014OPT'
CARTOES = ('mc0', 'mc1')
MANTER = 5   # backups guardados na box


class Interrompido(Exception):
    """O PS2 parou de responder (navegador fechado) no meio do trabalho."""


class Falha(Exception):
    pass


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 16), b''):
            h.update(bloco)
    return h.hexdigest()


class Atualizador:
    def __init__(self, op, pasta, aberto, buscar, log=print, progresso=None):
        """op(n, origem, destino, tam) -> bool (pedido ao navegador.elf); pasta = ps2/ (a raiz do host: do PS2);
        buscar(caminho) -> bytes (GET no servidor do notebook, com a chave); progresso(texto, pct) mostra o andamento
        na tela do PS2 (faixa do navegador) quase em tempo real."""
        self.op_ps2, self.aberto, self.buscar, self.log = op, aberto, buscar, log
        self.progresso, self._trava = progresso, threading.Lock()
        self.pasta = os.path.join(pasta, 'pes14')
        os.makedirs(self.pasta, exist_ok=True)
        self.arq_estado = os.path.join(self.pasta, 'estado.json')
        try:
            self.estado = json.load(open(self.arq_estado, encoding='utf-8'))
        except (OSError, ValueError):
            self.estado = {}
        self.estado['fase'] = ''

    # ---------- estado ----------
    def salvar(self):
        with self._trava:
            tmp = self.arq_estado + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.estado, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.arq_estado)

    def marca(self, texto, pct):
        """Etapa atual + porcentagem: vai para o estado.json (página /pes14) e para a faixa na tela do PS2."""
        self.estado['fase'], self.estado['pct'], self.estado['fase_t'] = texto, pct, time.time()
        self.salvar()
        if self.progresso:
            try:
                self.progresso(texto, pct)
            except Exception as e:
                self.log('pes14: progresso:', repr(e))

    def fase(self, texto):
        self.marca(texto, self.estado.get('pct') or 0)

    @contextlib.contextmanager
    def etapa(self, texto, p0, p1, estimado):
        """Etapa longa de um pedido só ao PS2 (sem andamento próprio): mostra os segundos e uma barra que anda de p0
        para p1 pela estimativa de duração e nunca chega em p1 antes de terminar."""
        parar, t0 = threading.Event(), time.time()

        def contar():
            while not parar.is_set():
                dt = time.time() - t0
                self.marca(f'{texto} {int(dt)}s', int(p0 + (p1 - p0) * (1 - math.exp(-dt / estimado))))
                parar.wait(1.0)

        th = threading.Thread(target=contar, daemon=True)
        th.start()
        try:
            yield
        finally:
            parar.set()
            th.join(3)
            self.marca(texto, p1)

    # ---------- pedidos ao PS2 ----------
    def op(self, n, origem, destino='-', tam=0):
        if not self.aberto():
            raise Interrompido()
        ok = self.op_ps2(n, origem, destino, tam)
        if not ok and not self.aberto():
            raise Interrompido()
        return ok

    def _local(self, *partes):
        return os.path.join(self.pasta, *partes)

    def listar(self, caminho):
        """[(pasta?, nome, tam)] ou None se a pasta não abriu."""
        saida = self._local('lista.txt')
        if os.path.exists(saida):
            os.remove(saida)
        if not self.op(8, caminho, 'host:pes14/lista.txt'):
            return None
        itens = []
        for l in open(saida, encoding='latin-1').read().splitlines():
            p = l.split('\t')
            if len(p) == 4:
                itens.append((p[0] == 'D', p[1], int(p[2] or 0)))
        return itens

    def achar_save(self, pasta_save):
        """(cartão, {nome: tamanho}) do primeiro cartão com a pasta do save; (None, None) se nenhum tem."""
        for c in CARTOES:
            itens = self.listar(f'{c}:/{pasta_save}')
            if itens:
                return c, {n: t for p, n, t in itens if not p}
        return None, None

    # ---------- passos ----------
    def baixar(self, manifesto):
        """Baixa e confere cada arquivo do manifesto para ps2/pes14/novo/<versão>/."""
        base = self._local('novo', manifesto['versao'])
        os.makedirs(base, exist_ok=True)
        for a in manifesto['arquivos']:
            destino = os.path.join(base, a['nome'])
            if os.path.exists(destino) and os.path.getsize(destino) == a['tam'] and sha256(destino) == a['sha256']:
                continue
            with self.etapa('Baixando do notebook', 8, 25, 5):
                dados = self.buscar(f'/pes14/{manifesto["pasta"]}/{a["nome"]}')
            tmp = destino + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(dados)
            if os.path.getsize(tmp) != a['tam'] or sha256(tmp) != a['sha256']:
                os.remove(tmp)
                raise Falha(f'o arquivo {a["nome"]} veio corrompido do notebook: nada foi gravado')
            os.replace(tmp, destino)
        return base

    def backup(self, cartao, pasta_save, atuais):
        """Copia o save atual do cartão para a box. Só devolve se cada cópia tem o tamanho certo."""
        ts = time.strftime('%Y%m%d-%H%M%S')
        dest = self._local('backup', ts)
        os.makedirs(dest, exist_ok=True)
        total, feito, p1 = sum(atuais.values()) or 1, 0, 25
        for nome, tam in atuais.items():
            p0, feito = p1, feito + tam   # a barra anda por tamanho e nunca recua
            p1 = max(p0, 25 + 25 * feito // total)
            with self.etapa('Guardando o save atual', p0, p1, max(1.0, 15 * tam / total)):
                lido = self.op(0, f'{cartao}:/{pasta_save}/{nome}', f'host:pes14/backup/{ts}/{nome}', tam)
            if not lido:
                raise Falha(f'não consegui ler {nome} do {cartao}: nada foi alterado')
            if os.path.getsize(os.path.join(dest, nome)) != tam:
                raise Falha(f'a cópia de {nome} ficou com tamanho errado: nada foi alterado')
        json.dump({'cartao': cartao, 'pasta': pasta_save, 'arquivos': atuais}, open(os.path.join(dest, 'INFO.json'), 'w'))
        antigos = sorted(d for d in os.listdir(self._local('backup')) if len(d) == 15)[:-MANTER]
        for d in antigos:
            shutil.rmtree(self._local('backup', d), ignore_errors=True)
        return ts, dest

    def gravar(self, cartao, pasta_save, nome, origem_host, esperado):
        """Grava um arquivo no cartão, lê de volta e compara o sha256."""
        tam = os.path.getsize(self._local(*origem_host.split('/')[1:]))
        with self.etapa(f'Gravando no {cartao}', 50, 80, 25):
            ok = self.op(0, f'host:{origem_host}', f'{cartao}:/{pasta_save}/{nome}', tam)
        verif = self._local('verif.bin')
        if os.path.exists(verif):
            os.remove(verif)
        if ok:
            with self.etapa('Conferindo o que gravou', 80, 97, 15):
                ok = self.op(0, f'{cartao}:/{pasta_save}/{nome}', 'host:pes14/verif.bin', tam)
        return bool(ok and os.path.exists(verif) and sha256(verif) == esperado)

    def voltar_backup(self, cartao, pasta_save, ts, atuais):
        """Desfaz: devolve ao cartão o que o backup guardou. True se tudo voltou conferido."""
        tudo = True
        for nome, tam in atuais.items():
            origem = f'host:pes14/backup/{ts}/{nome}'
            esperado = sha256(self._local('backup', ts, nome))
            tudo = self.gravar(cartao, pasta_save, nome, f'pes14/backup/{ts}/{nome}', esperado) and tudo
        return tudo

    # ---------- fluxo ----------
    def rodar(self, forcar=False):
        """Devolve (ok, mensagem)."""
        try:
            return self._rodar(forcar)
        except Interrompido:
            return self._fim(False, 'interrompido: o navegador fechou no meio. Confira o save e tente de novo '
                                    '(o save anterior está guardado na box).')
        except Falha as e:
            return self._fim(False, str(e))
        except Exception as e:
            self.log('pes14:', repr(e))
            return self._fim(False, f'erro inesperado: {e}')
        finally:
            self.estado['fase'] = ''
            self.salvar()

    def _fim(self, ok, msg):
        self.estado['resultado'] = {'ok': ok, 'msg': msg, 'quando': time.strftime('%d/%m/%Y %H:%M')}
        self.salvar()
        self.log('pes14:', msg)
        return ok, msg

    def _rodar(self, forcar):
        if not self.aberto():
            return self._fim(False, 'o navegador não está aberto no PS2')
        self.estado['resultado'] = {'ok': None, 'msg': 'Atualizando…'}
        self.marca('Falando com o notebook', 2)
        try:
            manifesto = json.loads(self.buscar('/pes14/manifest.json'))
        except Exception as e:
            raise Falha(f'o notebook não respondeu ({e}): nada foi alterado')
        if not manifesto.get('arquivos'):
            raise Falha('o notebook ainda não tem um save atualizado para baixar')
        pasta_save = manifesto.get('pasta') or PASTA_SAVE_PADRAO
        self.marca('Procurando o save do PES 14', 5)
        cartao, atuais = self.achar_save(pasta_save)
        if not cartao:
            raise Falha(f'não achei o save {pasta_save} no mc0 nem no mc1. Abra o PES 14 e salve o Option File '
                        'uma vez; depois tente de novo.')
        ja = self.estado.get('versao') == manifesto['versao'] and self.estado.get('cartao') == cartao
        if ja and not forcar:
            return self._fim(True, f'Já está na versão {manifesto["versao"]}.')
        novos = {a['nome'] for a in manifesto['arquivos']}
        if not novos <= set(atuais):
            raise Falha('o save do cartão não tem o arquivo esperado (' + ', '.join(sorted(novos - set(atuais)))
                        + '): não vou gravar nada')
        base = self.baixar(manifesto)
        ts, _ = self.backup(cartao, pasta_save, atuais)
        erros = []
        for a in manifesto['arquivos']:
            if not self.gravar(cartao, pasta_save, a['nome'], f'pes14/novo/{manifesto["versao"]}/{a["nome"]}', a['sha256']):
                erros.append(a['nome'])
        if erros:
            self.marca('Desfazendo: voltando o anterior', 50)
            voltou = self.voltar_backup(cartao, pasta_save, ts, atuais)
            return self._fim(False, f'a gravação de {", ".join(erros)} falhou na conferência. '
                             + ('O save anterior foi devolvido e conferido.' if voltou else
                                f'ATENÇÃO: não consegui conferir a devolução; o backup está em ps2/pes14/backup/{ts}.'))
        self.marca('Pronto', 100)
        self.estado.update(versao=manifesto['versao'], cartao=cartao, backup=ts, quando=time.strftime('%d/%m/%Y %H:%M'),
                           resumo=manifesto.get('resumo', {}))
        return self._fim(True, f'Save atualizado no {cartao} (versão {manifesto["versao"]}). '
                               f'Backup do anterior: {ts}. Abra o PES 14 para conferir.')

    def desfazer(self):
        """Devolve o último backup ao cartão (botão da página)."""
        try:
            if not self.aberto():
                return self._fim(False, 'o navegador não está aberto no PS2')
            pasta = self._local('backup')
            ts = (sorted(d for d in os.listdir(pasta) if len(d) == 15) or [''])[-1] if os.path.isdir(pasta) else ''
            if not ts:
                return self._fim(False, 'não há backup guardado')
            info = json.load(open(self._local('backup', ts, 'INFO.json')))
            ok = self.voltar_backup(info['cartao'], info['pasta'], ts, info['arquivos'])
            if ok:
                self.estado['versao'] = ''
            return self._fim(ok, f'Save de {ts} devolvido ao {info["cartao"]} e conferido.' if ok
                             else 'a devolução falhou na conferência: confira o cartão')
        except Interrompido:
            return self._fim(False, 'interrompido: o navegador fechou no meio')
        finally:
            self.estado['fase'] = ''
            self.salvar()
