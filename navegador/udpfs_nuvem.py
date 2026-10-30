#!/usr/bin/env python3
"""Servidor de jogos do Neutrino na TV box com "jogo em nuvem" (pedido do usuário 17/10/2026).

É o udpfs_server.py oficial do Neutrino 1.8 (pasta ~/udpfs_server) servindo o pendrive da box, com uma diferença:
quando o PS2 abre DVD/<jogo>.iso ou CD/<jogo>.iso que NÃO está no pendrive, o arquivo vem do HD do notebook pelo
videos_https.py (/iso/..., rede local em casa ou https://ps2videos.rodrigoflix.com fora), lido aos pedaços
enquanto o PS2 joga:
  - blocos de 1 MB guardados na memória (os 48 mais recentes) e uma thread que busca os 3 seguintes;
  - endereços e chave em ~/ps2nav/remoto.json (o mesmo do servidor_host.py).
Memory card na nuvem (22/10/2026): MC/<arquivo> não vem do pendrive, e sim de ~/ps2nav/mc (nuvem.py), e é o ÚNICO
lugar onde o PS2 pode gravar (o resto continua só leitura mesmo com --read-only); cada gravação avisa o nuvem.py,
que manda o cartão ao servidor 15 s depois da última.
Cinema na nuvem (22/10/2026, religado 23/10 a pedido do usuário): a raiz ganha a pasta virtual CINEMA-NUVEM com os vídeos de /cinema/lista do notebook
(formato do SMS); o SMS abre udpfs:/CINEMA-NUVEM/<vídeo> e ele vem de /cinema/<vídeo> aos pedaços, como os ISOs.
ISOs do celular (24/10/2026): o app PS2 Henbox serve os ISOs da memória do celular (HTTP com Range) e o central.py
anota a lista em ~/ps2nav/celular.json; DVD/<jogo>.iso que não está no pendrive e está nessa lista vem do celular,
do mesmo jeito que os do notebook (o celular vem antes do notebook).
Uso: udpfs_nuvem.py -d /storage/XXXX-XXXX --read-only   (os mesmos argumentos do udpfs_server.py)
"""
import errno, http.client, json, os, sys, threading, time, urllib.parse
from collections import OrderedDict

sys.path.insert(0, os.path.expanduser('~/udpfs_server'))
import udpfs_server as U   # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nuvem   # noqa: E402

REMOTO = os.path.expanduser('~/ps2nav/remoto.json')
CELULAR = os.path.expanduser('~/ps2nav/celular.json')
BLOCO, GUARDA, ADIANTE = 1 << 20, 48, 3
# antecipação adaptativa (24/10/2026): leitura sequencial rápida (o carregamento de jogo) ganha mais
# blocos sendo buscados à frente, leitura com saltos volta para a antecipação mínima. O objetivo é usar a
# banda sobrando no começo do jogo (a parte que o jogador nota) sem encher o cache com lixo depois do salto.
ADI_MAX, ADIMIN = 40, ADIANTE    # 40 MB de janela cabe no GUARDA (48 MB) e sobra para o pedido "fora de série"
_url_boa = ['']


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def cfg():
    try:
        return json.load(open(REMOTO))
    except (OSError, ValueError):
        return {}


class IsoRemoto:
    """Arquivo do notebook com cara de arquivo local (read/seek/tell/close), para o udpfs_server.py."""

    def __init__(self, relativo, prefixo='/iso/', urls=None, chave=None):
        c = cfg() if urls is None else {'urls': urls, 'chave': chave or ''}
        self.chave, self.caminho = c.get('chave', ''), prefixo + urllib.parse.quote(relativo)
        self.url, self.tam = None, None
        for url in sorted(c.get('urls', []), key=lambda u: u != _url_boa[0]):
            u = urllib.parse.urlparse(url)
            try:
                con = self._conexao(u, 3 if u.scheme == 'http' else 15)
                con.request('HEAD', self.caminho, headers={'X-Chave': self.chave})
                r = con.getresponse(); r.read(); con.close()
                if r.status == 200:
                    self.url, self.tam = u, int(r.getheader('Content-Length', '0'))
                    if urls is None:
                        _url_boa[0] = url
                    break
                if r.status == 404:
                    raise FileNotFoundError(relativo)
            except FileNotFoundError:
                raise
            except Exception as e:
                log('nuvem:', url, e)
        if self.url is None:
            raise OSError(errno.EHOSTUNREACH, 'notebook fora do alcance')
        self.pos = 0
        self.blocos, self.trava = OrderedDict(), threading.Lock()
        self.pedidos, self.cond, self.fechado = set(), threading.Condition(), False
        self.adiante, self._amost = ADIANTE, []   # janela dinâmica (_amost[(pos, t)] das últimas leituras)
        self.con = self._conexao(self.url, 20)
        threading.Thread(target=self._antecipar, daemon=True).start()
        log(f'nuvem: abrindo {relativo} ({self.tam >> 20} MB) por {self.url.netloc}')

    @staticmethod
    def _conexao(u, timeout):
        Cls = http.client.HTTPSConnection if u.scheme == 'https' else http.client.HTTPConnection
        return Cls(u.netloc, timeout=timeout)

    def _baixar(self, n, con):
        ini = n * BLOCO
        fim = min(ini + BLOCO, self.tam) - 1
        for tentativa in range(4):
            try:
                con.request('GET', self.caminho, headers={'X-Chave': self.chave, 'Range': f'bytes={ini}-{fim}'})
                r = con.getresponse(); d = r.read()
                if r.status in (200, 206) and len(d) == fim - ini + 1:
                    return d, con
                raise OSError(f'HTTP {r.status}, {len(d)} bytes')
            except Exception as e:
                log(f'nuvem: bloco {n} tentativa {tentativa + 1}: {e}')
                con.close(); time.sleep(0.5 * (tentativa + 1))
                con = self._conexao(self.url, 20)
        raise OSError(errno.EIO, f'não consegui ler o bloco {n}')

    def _guardar(self, n, d):
        with self.trava:
            self.blocos[n] = d
            self.blocos.move_to_end(n)
            while len(self.blocos) > GUARDA:
                self.blocos.popitem(last=False)

    def _bloco(self, n):
        with self.trava:
            d = self.blocos.get(n)
            if d is not None:
                self.blocos.move_to_end(n)
                return d
        d, self.con = self._baixar(n, self.con)
        self._guardar(n, d)
        return d

    def _antecipar(self):
        """Busca os blocos logo depois do que o PS2 está lendo (o carregamento de jogo é quase sempre em sequência)."""
        con = self._conexao(self.url, 20)
        ultimo = -1
        while not self.fechado:
            with self.cond:
                self.cond.wait(0.5)
            base = self.pos // BLOCO
            for n in range(base + 1, min(base + 1 + self.adiante, (self.tam + BLOCO - 1) // BLOCO)):
                if self.fechado:
                    break
                with self.trava:
                    tem = n in self.blocos
                if not tem and n != ultimo:
                    try:
                        d, con = self._baixar(n, con)
                        self._guardar(n, d)
                        ultimo = n
                    except OSError:
                        break
        con.close()

    def _amedir(self, antes, depois):
        """Ajusta a janela antecipada pela velocidade de leitura sequencial recente do PS2."""
        agora = time.time()
        a = self._amost
        if a and (antes != a[-1][1] or agora - a[-1][2] > 10):
            a.clear()          # o PS2 saltou para outro lugar (tela diferente, menu): a sequência acabou
            self.adiante = ADIMIN
        a.append((antes, depois, agora))
        if len(a) > 24:
            a.pop(0)
        if len(a) < 3:
            return
        ini, fim = a[0], a[-1]
        total, dur = fim[1] - ini[0], fim[2] - ini[2]
        if dur < 5 or total <= 0:
            return
        vel = (total / dur) / 1048576.0
        alvo = min(ADI_MAX, max(ADIMIN, int(3 + vel * 5)))
        if alvo != self.adiante:
            log(f'nuvem: leitura {vel:.1f} MB/s, antecipando {alvo} MB à frente')
            self.adiante = alvo

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.tam - self.pos
        n = max(0, min(n, self.tam - self.pos))
        partes = []
        antes = self.pos
        while n > 0:
            b, desl = divmod(self.pos, BLOCO)
            d = self._bloco(b)[desl:desl + n]
            partes.append(d)
            self.pos += len(d)
            n -= len(d)
        self._amedir(antes, self.pos)
        with self.cond:
            self.cond.notify_all()
        return b''.join(partes)

    def seek(self, ofs, de=0):
        self.pos = ofs if de == 0 else (self.pos + ofs if de == 1 else self.tam + ofs)
        return self.pos

    def tell(self):
        return self.pos

    def write(self, d):
        raise OSError(errno.EROFS, 'jogo em nuvem é só leitura')

    def close(self):
        self.fechado = True
        with self.cond:
            self.cond.notify_all()
        try:
            self.con.close()
        except Exception:
            pass


def celular_lista():
    """{"url", "chave", "isos": [{"i", "nome", "tam", ...}]} do celular registrado (central.py), ou {}."""
    try:
        return json.load(open(CELULAR, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def iso_celular(nome):
    """O ISO <nome> servido pelo app do celular (FileNotFoundError se o celular não tem)."""
    c = celular_lista()
    iso = next((x for x in c.get('isos', []) if x.get('nome') == nome), None)
    if not iso or not c.get('url'):
        raise FileNotFoundError(nome)
    return IsoRemoto(f"{iso['i']}/{nome}", '/iso/', urls=[c['url']], chave=c.get('chave', ''))


def abrir_remoto(rel):
    """DVD/<jogo>.iso fora do pendrive: do celular, se ele tiver; senão do notebook."""
    try:
        return iso_celular(os.path.basename(rel))
    except FileNotFoundError:
        pass
    except OSError as e:
        log('celular:', rel, e)
    return IsoRemoto(rel)


def _relativo(caminho):
    caminho = caminho.replace('\\', '/').lstrip('/')
    pasta = caminho.split('/', 1)[0].upper()
    if pasta in ('DVD', 'CD') and caminho.lower().endswith('.iso') and '/' in caminho:
        return pasta + '/' + os.path.basename(caminho)
    return None


CINEMA = 'CINEMA-NUVEM'
_cinema_cache = [0.0, []]


def _cinema(caminho):
    """'' para a pasta CINEMA-NUVEM, o nome do vídeo para CINEMA-NUVEM/<vídeo>, None se não for dela."""
    partes = caminho.replace('\\', '/').strip('/').split('/')
    if partes[0].upper() != CINEMA:
        return None
    return '' if len(partes) == 1 else (partes[1] if len(partes) == 2 else None)


def cinema_lista():
    """[{"nome", "tam"}] do notebook (guardada 60 s; o SMS reabre a pasta várias vezes)."""
    if time.time() - _cinema_cache[0] < 60:
        return _cinema_cache[1]
    c = cfg()
    for url in sorted(c.get('urls', []), key=lambda u: u != _url_boa[0]):
        u = urllib.parse.urlparse(url)
        try:
            con = IsoRemoto._conexao(u, 3 if u.scheme == 'http' else 15)
            con.request('GET', '/cinema/lista', headers={'X-Chave': c.get('chave', '')})
            r = con.getresponse(); d = r.read(); con.close()
            if r.status == 200:
                _cinema_cache[:] = [time.time(), json.loads(d)]
                return _cinema_cache[1]
        except Exception as e:
            log('cinema:', url, e)
    return _cinema_cache[1]


class _Entrada:
    """Item de pasta com cara de os.DirEntry (o udpfs_server só usa name, path e stat)."""

    def __init__(self, nome, tam=0, pasta=False):
        self.name, self.path = nome, nome
        agora = time.time()
        self._st = os.stat_result(((0o40755 if pasta else 0o100644), 0, 0, 1, 0, 0, tam, agora, agora, agora))

    def stat(self, follow_symlinks=True):
        return self._st


def _stat_remoto(srv, tam):
    agora = srv._encode_time(time.time())
    return {'mode': U.FIO_S_IFREG, 'attr': 0, 'size': tam & 0xFFFFFFFF, 'hisize': (tam >> 32) & 0xFFFFFFFF,
            'ctime': agora, 'atime': agora, 'mtime': agora}


def _caminho_mc(caminho):
    """MC/<arquivo> → ~/ps2nav/mc/<arquivo> (None se não for da pasta MC ou sair dela)."""
    caminho = caminho.replace('\\', '/').lstrip('/')
    if caminho.split('/', 1)[0].upper() != 'MC':
        return None
    resto = caminho.split('/', 1)[1] if '/' in caminho else ''
    os.makedirs(nuvem.MC_DIR, exist_ok=True)
    raiz = os.path.realpath(nuvem.MC_DIR)
    alvo = os.path.realpath(os.path.join(raiz, resto))
    return alvo if alvo == raiz or alvo.startswith(raiz + os.sep) else None


class ServidorNuvem(U.UdpfsServer):
    mc_handles = set()

    def _resolve_path(self, client_path):
        mc = _caminho_mc(client_path)
        return mc if mc else super()._resolve_path(client_path)

    def _escrevendo_mc(self, metodo, addr, payload, handle):
        """Libera a gravação só para arquivos abertos em MC/ (o laço do udpfs é uma thread só)."""
        if handle not in self.mc_handles:
            return metodo(addr, payload)
        self.read_only = False
        try:
            metodo(addr, payload)
        finally:
            self.read_only = True
        nuvem.mc_marcar()

    def _handle_bwrite_req(self, addr, payload):
        h = U.struct.unpack('<BBHiII', payload[:16])[3] if len(payload) >= 16 else None
        return self._escrevendo_mc(super()._handle_bwrite_req, addr, payload, h)

    def _handle_write_req(self, addr, payload):
        h = U.struct.unpack('<BBBBiI', payload[:12])[4] if len(payload) >= 12 else None
        return self._escrevendo_mc(super()._handle_write_req, addr, payload, h)

    def _handle_close(self, addr, payload):
        if len(payload) >= 8:
            self.mc_handles.discard(U.struct.unpack('<BBBBi', payload[:8])[4])
        return super()._handle_close(addr, payload)

    def _caminho_e_remoto(self, payload, inicio):
        caminho = payload[inicio:].split(b'\x00')[0].decode('utf-8', errors='replace')
        local = self._resolve_path(caminho)
        rel = _relativo(caminho)
        if rel and local and not os.path.exists(local) and not self._find_compressed_version(local):
            return caminho, rel
        return caminho, None

    def _abrir_cinema(self, addr, caminho, nome, is_dir, flags):
        self.stats['open'] += 1
        if nome == '' and is_dir:
            itens = [_Entrada(v['nome'], v['tam']) for v in cinema_lista()]
            h = self._alloc_handle({'entries': itens, 'index': 0}, is_dir=True)
            self._print_event(f"[{addr[0]}:{addr[1]}] DOPEN '{caminho}' -> handle={h} ({len(itens)} vídeos na nuvem)")
            return self._send_open_reply(addr, h, stat_info=self._stat_to_bytes(_Entrada(CINEMA, pasta=True).stat()))
        if is_dir or not nome:
            return self._send_open_reply(addr, -errno.ENOENT)
        if flags & 0x02:
            return self._send_open_reply(addr, -errno.EACCES)
        try:
            f = IsoRemoto(nome, '/cinema/')
        except FileNotFoundError:
            return self._send_open_reply(addr, -errno.ENOENT)
        except OSError as e:
            log('cinema:', caminho, e)
            return self._send_open_reply(addr, -errno.EIO)
        h = self._alloc_handle(f, is_dir=False)
        if h < 0:
            f.close()
            return self._send_open_reply(addr, h)
        self._print_event(f"[{addr[0]}:{addr[1]}] OPEN '{caminho}' -> handle={h}, size={f.tam} (cinema na nuvem)")
        return self._send_open_reply(addr, h, stat_info=_stat_remoto(self, f.tam))

    def _handle_open(self, addr, payload):
        if len(payload) >= 8:
            _, is_dir, flags, _ = U.struct.unpack('<BBHi', payload[:8])
            caminho, rel = self._caminho_e_remoto(payload, 8)
            nome_cinema = _cinema(caminho)
            if nome_cinema is not None:
                return self._abrir_cinema(addr, caminho, nome_cinema, is_dir, flags)
            if is_dir and self.root_dir and self._resolve_path(caminho) == self.root_dir:
                # raiz: o que está no pendrive + a pasta virtual CINEMA-NUVEM
                antes = set(self.handles)
                super()._handle_open(addr, payload)
                for h in set(self.handles) - antes:
                    if self.handles[h].is_dir:
                        self.handles[h].obj['entries'].append(_Entrada(CINEMA, pasta=True))
                return
            if _caminho_mc(caminho) and not is_dir:   # memory card: abre com gravação liberada
                antes = set(self.handles)
                self.read_only = False
                try:
                    super()._handle_open(addr, payload)
                finally:
                    self.read_only = True
                novos = set(self.handles) - antes
                self.mc_handles |= novos
                if novos:
                    log('memory card aberto pelo PS2:', caminho)
                return
            if rel and not is_dir:
                self.stats['open'] += 1
                if flags & 0x02:
                    return self._send_open_reply(addr, -errno.EACCES)
                try:
                    f = abrir_remoto(rel)
                except FileNotFoundError:
                    return self._send_open_reply(addr, -errno.ENOENT)
                except OSError as e:
                    log('nuvem:', caminho, e)
                    return self._send_open_reply(addr, -errno.EIO)
                h = self._alloc_handle(f, is_dir=False)
                if h < 0:
                    f.close()
                    return self._send_open_reply(addr, h)
                self._print_event(f"[{addr[0]}:{addr[1]}] OPEN '{caminho}' -> handle={h}, size={f.tam} (nuvem)")
                return self._send_open_reply(addr, h, stat_info=_stat_remoto(self, f.tam))
        return super()._handle_open(addr, payload)

    def _handle_getstat(self, addr, payload):
        if len(payload) >= 4:
            caminho, rel = self._caminho_e_remoto(payload, 4)
            nome_cinema = _cinema(caminho)
            if nome_cinema == '':
                self.stats['getstat'] += 1
                return self._send_getstat_reply(addr, result=0,
                                                stat_info=self._stat_to_bytes(_Entrada(CINEMA, pasta=True).stat()))
            if nome_cinema:
                self.stats['getstat'] += 1
                v = next((v for v in cinema_lista() if v['nome'] == nome_cinema), None)
                if v is None:
                    return self._send_getstat_reply(addr, result=-errno.ENOENT)
                return self._send_getstat_reply(addr, result=0, stat_info=_stat_remoto(self, v['tam']))
            if rel:
                self.stats['getstat'] += 1
                try:
                    f = abrir_remoto(rel)
                    tam = f.tam
                    f.close()
                except FileNotFoundError:
                    return self._send_getstat_reply(addr, result=-errno.ENOENT)
                except OSError:
                    return self._send_getstat_reply(addr, result=-errno.EIO)
                return self._send_getstat_reply(addr, result=0, stat_info=_stat_remoto(self, tam))
        return super()._handle_getstat(addr, payload)


if __name__ == '__main__':
    U.UdpfsServer = ServidorNuvem   # o main() oficial monta o servidor com esta classe
    threading.Thread(target=nuvem.mc_vigiar, daemon=True).start()
    U.main()
