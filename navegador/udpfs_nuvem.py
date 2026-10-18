#!/usr/bin/env python3
"""Servidor de jogos do Neutrino na TV box com "jogo em nuvem" (pedido do usuário 17/10/2026).

É o udpfs_server.py oficial do Neutrino 1.8 (pasta ~/udpfs_server) servindo o pendrive da box, com uma diferença:
quando o PS2 abre DVD/<jogo>.iso ou CD/<jogo>.iso que NÃO está no pendrive, o arquivo vem do HD do notebook pelo
videos_https.py (/iso/..., rede local em casa ou https://ps2videos.rodrigoflix.com fora), lido aos pedaços
enquanto o PS2 joga:
  - blocos de 1 MB guardados na memória (os 48 mais recentes) e uma thread que busca os 3 seguintes;
  - endereços e chave em ~/ps2nav/remoto.json (o mesmo do servidor_host.py).
Uso: udpfs_nuvem.py -d /storage/XXXX-XXXX --read-only   (os mesmos argumentos do udpfs_server.py)
"""
import errno, http.client, json, os, sys, threading, time, urllib.parse
from collections import OrderedDict

sys.path.insert(0, os.path.expanduser('~/udpfs_server'))
import udpfs_server as U   # noqa: E402

REMOTO = os.path.expanduser('~/ps2nav/remoto.json')
BLOCO, GUARDA, ADIANTE = 1 << 20, 48, 3
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

    def __init__(self, relativo):
        c = cfg()
        self.chave, self.caminho = c.get('chave', ''), '/iso/' + urllib.parse.quote(relativo)
        self.url, self.tam = None, None
        for url in sorted(c.get('urls', []), key=lambda u: u != _url_boa[0]):
            u = urllib.parse.urlparse(url)
            try:
                con = self._conexao(u, 3 if u.scheme == 'http' else 15)
                con.request('HEAD', self.caminho, headers={'X-Chave': self.chave})
                r = con.getresponse(); r.read(); con.close()
                if r.status == 200:
                    self.url, self.tam = u, int(r.getheader('Content-Length', '0'))
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
            for n in range(base + 1, min(base + 1 + ADIANTE, (self.tam + BLOCO - 1) // BLOCO)):
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

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.tam - self.pos
        n = max(0, min(n, self.tam - self.pos))
        partes = []
        while n > 0:
            b, desl = divmod(self.pos, BLOCO)
            d = self._bloco(b)[desl:desl + n]
            partes.append(d)
            self.pos += len(d)
            n -= len(d)
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


def _relativo(caminho):
    caminho = caminho.replace('\\', '/').lstrip('/')
    pasta = caminho.split('/', 1)[0].upper()
    if pasta in ('DVD', 'CD') and caminho.lower().endswith('.iso') and '/' in caminho:
        return pasta + '/' + os.path.basename(caminho)
    return None


def _stat_remoto(srv, tam):
    agora = srv._encode_time(time.time())
    return {'mode': U.FIO_S_IFREG, 'attr': 0, 'size': tam & 0xFFFFFFFF, 'hisize': (tam >> 32) & 0xFFFFFFFF,
            'ctime': agora, 'atime': agora, 'mtime': agora}


class ServidorNuvem(U.UdpfsServer):
    def _caminho_e_remoto(self, payload, inicio):
        caminho = payload[inicio:].split(b'\x00')[0].decode('utf-8', errors='replace')
        local = self._resolve_path(caminho)
        rel = _relativo(caminho)
        if rel and local and not os.path.exists(local) and not self._find_compressed_version(local):
            return caminho, rel
        return caminho, None

    def _handle_open(self, addr, payload):
        if len(payload) >= 8:
            _, is_dir, flags, _ = U.struct.unpack('<BBHi', payload[:8])
            caminho, rel = self._caminho_e_remoto(payload, 8)
            if rel and not is_dir:
                self.stats['open'] += 1
                if flags & 0x02:
                    return self._send_open_reply(addr, -errno.EACCES)
                try:
                    f = IsoRemoto(rel)
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
            if rel:
                self.stats['getstat'] += 1
                try:
                    f = IsoRemoto(rel)
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
    U.main()
