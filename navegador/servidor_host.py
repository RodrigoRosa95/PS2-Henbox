#!/usr/bin/env python3
"""Servidor host: do navegador do PS2 sem o PS2Link (pedido do usuário 17/10/2026: rede direto no PS2).

Quando o navegador.elf é aberto pelo OPL (pendrive), ele liga a rede sozinho e carrega o navlink.irx: o servidor de
arquivos host: do PS2Link (mesmo protocolo do ps2client) na porta TCP 0x4721. O PS2 escuta; este programa tenta
conectar a cada 2 s e, conectado, serve a pasta navegador/ps2/ — os mesmos dif.bin, entrada.bin, pedido.bin, vídeos
e ROMs que o ps2client serve no modo PS2Link. Assim o navegador_servidor.py não muda nada.

Protocolo (big-endian, ps2link/include/hostlink.h): cabeçalho cmd:u32 len:u16 (len inclui o cabeçalho).
  open  0xbabe0111 flags:i32 path[256]   → 0xbabe0112 retval:i32
  close 0xbabe0121 fd:i32                → 0xbabe0122 retval
  read  0xbabe0131 fd:i32 nbytes:i32     → 0xbabe0132 retval:i32 nbytes:i32 + os dados
  write 0xbabe0141 fd:i32 nbytes:i32 + dados (fora do len) → 0xbabe0142 retval
  lseek 0xbabe0151 fd offset whence      → 0xbabe0152 retval
  remove/rmdir name[256], mkdir mode name[256], getstat name[256], dopen/dread/dclose
Uso: servidor_host.py [IP do PS2]   (padrão 192.168.4.230)

PS2Link abre o navegador (22/10/2026): se o PS2 estiver no PS2Link (porta TCP 0x4711, o mesmo protocolo de arquivos),
este programa faz o papel do ps2client — serve host: e manda o comando execee (UDP 0x4712) "host:navegador.elf rede".
O navegador aberto assim é o caminho que abre os jogos pela rede (aberto direto pelo OPL, o Neutrino travava).
PS2_AUTO_NAVEGADOR=0 desliga.
"""
import os, re, socket, stat, struct, subprocess, sys, threading, time

PS2 = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PS2_IP', '192.168.4.230')
PORTA = 0x4721
PORTA_PS2LINK, PORTA_CMD = 0x4711, 0x4712
EXECEE = 0xBABE0203
AUTO_NAVEGADOR = os.environ.get('PS2_AUTO_NAVEGADOR', '1') != '0'
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ps2')
CAB = struct.Struct('>IH')


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


# Conquistas (23/10/2026): ps2/jogos-box é um link para a pasta DVD do pendrive desta box, para o PS2 copiar o ISO
# para o pendrive dele (o OPL-RA só tem conquistas com o jogo no USB do próprio console). Na prática só leitura: o
# Android não deixa o Termux gravar no pendrive USB.
JOGOS_BOX = os.path.join(RAIZ, 'jogos-box')


def caminho(nome):
    """host:X → navegador/ps2/X, sem sair da pasta."""
    nome = nome.split(b'\0', 1)[0].decode('latin-1').replace('\\', '/').lstrip('/')
    if nome.startswith('host:'):
        nome = nome[5:].lstrip('/')
    final = os.path.realpath(os.path.join(RAIZ, nome))
    if final != RAIZ and not final.startswith(RAIZ + os.sep):
        externo = os.path.realpath(JOGOS_BOX)
        if not (os.path.islink(JOGOS_BOX) and final.startswith(externo + os.sep)):
            raise PermissionError(nome)
    return final


def flags_os(f):
    modo = {1: os.O_RDONLY, 2: os.O_WRONLY, 3: os.O_RDWR}.get(f & 3, os.O_RDONLY)
    if f & 0x100: modo |= os.O_APPEND
    if f & 0x200: modo |= os.O_CREAT
    if f & 0x400: modo |= os.O_TRUNC
    return modo


def receber(s, n):
    b = bytearray()
    while len(b) < n:
        p = s.recv(n - len(b))
        if not p:
            raise ConnectionError('PS2 desconectou')
        b += p
    return bytes(b)


def stat_ps2(st):
    """mode/attr/size + 3 datas de 8 bytes + hisize (fio_stat_t do PS2)."""
    modo = 0x1000 if stat.S_ISDIR(st.st_mode) else 0x2000   # FIO_S_IFDIR / FIO_S_IFREG
    modo |= 0x1FF
    datas = b''
    for t in (st.st_ctime, st.st_atime, st.st_mtime):
        tm = time.localtime(t)
        datas += struct.pack('<BBBBBBH', 0, tm.tm_sec, tm.tm_min, tm.tm_hour, tm.tm_mday, tm.tm_mon, tm.tm_year)
    return struct.pack('>III', modo, 0, st.st_size & 0xFFFFFFFF) + datas + struct.pack('>I', st.st_size >> 32)


def servir(s):
    fds, dirs, prox = {}, {}, [1]

    def novo(obj, tabela):
        n = prox[0]; prox[0] += 1
        tabela[n] = obj
        return n

    def resp(cmd, *vals, extra=b'', conta_extra=True):
        """len do cabeçalho conta o extra (getstat/dread: campos do pacote), menos no read, onde os dados vêm
        depois do pacote (ps2link pko_read_file). Contar errado deixa bytes sobrando e a resposta seguinte sai
        desalinhada: o Neutrino via -1 no open do compat.toml (17/10/2026)."""
        corpo = struct.pack('>' + 'i' * len(vals), *vals)
        tam = CAB.size + len(corpo) + (len(extra) if conta_extra else 0)
        s.sendall(CAB.pack(cmd, tam) + corpo + extra)

    try:
        while True:
            cmd, tam = CAB.unpack(receber(s, CAB.size))
            corpo = receber(s, tam - CAB.size)
            if cmd == 0xbabe0111:   # open
                fl, = struct.unpack('>i', corpo[:4])
                nome = corpo[4:].split(b'\0', 1)[0].decode('latin-1').lstrip('/')
                try:
                    if nome.startswith('host:'):
                        nome = nome[5:].lstrip('/')
                    r = novo(os.open(caminho(corpo[4:]), flags_os(fl), 0o644), fds)
                    if nome not in ('dif.bin', 'completa.bin', 'entrada.bin', 'pedido.bin', 'temperatura.txt'):
                        log('abriu', nome)
                except OSError as e:
                    r = -1
                resp(0xbabe0112, r)
            elif cmd == 0xbabe0121:   # close
                fd, = struct.unpack('>i', corpo[:4])
                r = -1
                if fd in fds:
                    f = fds.pop(fd)
                    os.close(f)
                    r = 0
                resp(0xbabe0122, r)
            elif cmd == 0xbabe0131:   # read
                fd, n = struct.unpack('>ii', corpo[:8])
                try:
                    f = fds[fd]
                    dados = os.read(f, max(0, n))
                    resp(0xbabe0132, len(dados), len(dados), extra=dados, conta_extra=False)
                except (KeyError, OSError):
                    resp(0xbabe0132, -1, 0)
            elif cmd == 0xbabe0141:   # write: os dados vêm logo depois do cabeçalho
                fd, n = struct.unpack('>ii', corpo[:8])
                dados = receber(s, n)
                try:
                    r = os.write(fds[fd], dados)
                except (KeyError, OSError):
                    r = -1
                resp(0xbabe0142, r)
            elif cmd == 0xbabe0151:   # lseek
                fd, ofs, de = struct.unpack('>iii', corpo[:12])
                try:
                    f = fds[fd]
                    r = os.lseek(f, ofs, de)
                except (KeyError, OSError):
                    r = -1
                resp(0xbabe0152, r)
            elif cmd in (0xbabe0191, 0xbabe01b1):   # remove, rmdir
                try:
                    (os.remove if cmd == 0xbabe0191 else os.rmdir)(caminho(corpo)); r = 0
                except OSError:
                    r = -1
                resp(cmd + 1, r)
            elif cmd == 0xbabe01a1:   # mkdir
                try:
                    os.mkdir(caminho(corpo[4:])); r = 0
                except OSError:
                    r = -1
                resp(0xbabe01a2, r)
            elif cmd == 0xbabe01c1:   # getstat
                try:
                    resp(0xbabe01c2, 0, extra=stat_ps2(os.stat(caminho(corpo))))
                except OSError:
                    resp(0xbabe01c2, -1, extra=bytes(40))
            elif cmd == 0xbabe0161:   # dopen
                try:
                    p = caminho(corpo[4:])
                    r = novo([p, sorted(os.listdir(p))], dirs)
                except OSError:
                    r = -1
                resp(0xbabe0162, r)
            elif cmd == 0xbabe0181:   # dread
                fd, = struct.unpack('>i', corpo[:4])
                d = dirs.get(fd)
                if not d or not d[1]:
                    resp(0xbabe0182, 0, extra=bytes(40 + 256))
                else:
                    nome = d[1].pop(0)
                    try:
                        info = stat_ps2(os.stat(os.path.join(d[0], nome)))
                    except OSError:
                        info = bytes(40)
                    resp(0xbabe0182, 1, extra=info + nome.encode('latin-1', 'replace')[:255].ljust(256, b'\0'))
            elif cmd == 0xbabe0171:   # dclose
                fd, = struct.unpack('>i', corpo[:4])
                resp(0xbabe0172, 0 if dirs.pop(fd, None) else -1)
            else:
                log('comando desconhecido', hex(cmd))
                return
    finally:
        for f in fds.values():
            os.close(f)


def redes_locais():
    """Prefixos /24 das interfaces desta máquina (ex.: '192.168.4.'), tirados do 'ip -o -4 addr'."""
    try:
        saida = subprocess.run(['ip', '-o', '-4', 'addr'], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    prefixos = []
    for m in re.finditer(r'inet (\d+\.\d+\.\d+)\.\d+/(\d+)', saida):
        if not m.group(1).startswith('127.') and 16 <= int(m.group(2)) <= 24 and m.group(1) + '.' not in prefixos:
            prefixos.append(m.group(1) + '.')
    return prefixos


def procurar_ps2():
    """Acha o PS2 sozinho (17/10/2026): o navegador.elf escuta na porta 0x4721; tenta todos os endereços das redes
    locais em paralelo (~2 s). Devolve o IP ou None."""
    achado = []
    def tentar(ip):
        if achado:
            return
        for porta in (PORTA, PORTA_PS2LINK):   # navegador aberto ou PS2Link esperando
            try:
                with socket.create_connection((ip, porta), timeout=1.2):
                    achado.append(ip)
                    return
            except OSError:
                pass
    proprio = PS2.rsplit('.', 1)[0] + '.'   # a rede do IP configurado vem primeiro
    for prefixo in [proprio] + [p for p in redes_locais() if p != proprio]:
        ts = [threading.Thread(target=tentar, args=(prefixo + str(i),), daemon=True) for i in range(1, 255)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        if achado:
            return achado[0]
    return None


def execee(ip, *args):
    """O comando execee do ps2client: cmd, len, argc e os argumentos separados por zero (256 bytes)."""
    dados = b''.join(a.encode() + b'\0' for a in args).ljust(256, b'\0')[:256]
    pacote = struct.pack('>IHi', EXECEE, 4 + 2 + 4 + 256, len(args)) + dados
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
        u.sendto(pacote, (ip, PORTA_CMD))


def pelo_ps2link():
    """PS2 no PS2Link: serve host: na porta dele e manda abrir o navegador. True se encontrou o PS2Link."""
    try:
        s = socket.create_connection((PS2, PORTA_PS2LINK), timeout=1.5)
    except OSError:
        return False
    s.settimeout(20)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    log('PS2Link encontrado: abrindo o navegador por ele')
    # versão de teste (23/10/2026): com ps2/NAVEGADOR_TESTE.txt contendo o nome do .elf, o PS2Link abre esse no lugar
    # do navegador.elf (que continua sendo o que vai para o pendrive na atualização automática)
    try:
        teste = open(os.path.join(RAIZ, 'NAVEGADOR_TESTE.txt')).read().strip()
    except OSError:
        teste = ''
    elf = teste if re.fullmatch(r'[\w.-]+\.elf', teste or '') and os.path.exists(os.path.join(RAIZ, teste)) else 'navegador.elf'
    threading.Timer(1.0, execee, args=(PS2, 'host:' + elf, 'rede')).start()
    try:
        servir(s)   # até o navegador reiniciar o IOP (a conexão cai) e ligar a rede própria dele
    except (ConnectionError, OSError) as e:
        log('PS2Link: conexão encerrada:', e)
    finally:
        s.close()
    return True


_ultimo_ps2link = [0]


def main():
    global PS2
    log(f'esperando o navegador no PS2 ({PS2}:{PORTA:#x}, ou procurando na rede), servindo {RAIZ}')
    falhas = 0
    while True:
        try:
            s = socket.create_connection((PS2, PORTA), timeout=1.5)
            falhas = 0
        except OSError:
            falhas += 1
            if AUTO_NAVEGADOR and time.time() - _ultimo_ps2link[0] > 30 and pelo_ps2link():
                _ultimo_ps2link[0] = time.time()   # não insiste se o navegador não subir: espera 30 s
                falhas = 0
                time.sleep(2)
                continue
            if falhas % 5 == 0:   # ~10 s sem resposta no IP conhecido: procura nas redes locais
                ip = procurar_ps2()
                if ip and ip != PS2:
                    log(f'PS2 encontrado em {ip} (antes {PS2})')
                    PS2 = ip
                    continue
            time.sleep(2)
            continue
        s.settimeout(20)   # o navegador pede várias vezes por segundo: 20 s calado = PS2 reiniciou/desligou (reconecta)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        log('PS2 conectado (navegador sem PS2Link)')
        try:
            servir(s)
        except (ConnectionError, OSError) as e:
            log('conexão encerrada:', e)
        finally:
            s.close()
        time.sleep(1)


if __name__ == '__main__':
    main()
