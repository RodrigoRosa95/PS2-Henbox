import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import struct
M=0x7ab3684c
def blocos(d):
    """lista (inicio_dados, tamanho, chk_gravado) varrendo cabeçalhos [tam][chk][0x200]"""
    w=lambda o:struct.unpack_from('<I',d,o)[0]
    res=[];o=0
    while o+12<=len(d):
        if w(o+8)==0x200 and 0<w(o)<=len(d):
            # tamanho do bloco = w(o) ; dados em o+12
            res.append((o+12,w(o),w(o+4)));o=o+12+w(o)
            while o<len(d) and w(o)==0: o+=4   # preenchimento zero
        else: o+=4
    return res

import re
_src=open(BASE+'/ref/PESEditor/src/editor/OptionFile.java').read()   # chave de 446 palavras: veja docs/FORMATO.md
KEY=[int(x) for x in re.findall(r'-?\d+',re.search(r'key = \{(.*?)\};',_src,re.S).group(1))]
BL=[(0xc,4852),(0x1418,2296),(0x1db8,4224),(0x2e44,22816),(0x8770,605120),(0x9c678,90227),(0xb26f8,11440),(0xb53b4,163432),(0xdd228,155624),(0x10321c,2596),(0x1040fc,20456)]
def dec(d,ini,tam,per=446):
    o=bytearray(d);k=0
    for a in range(ini,ini+tam-3,4):
        c=struct.unpack_from('<I',d,a)[0]
        p=((((c-KEY[k])&0xffffffff)+M)&0xffffffff)^M
        struct.pack_into('<I',o,a,p);k=(k+1)%per
    return bytes(o)

def enc(d,ini,tam,per=446):
    o=bytearray(d);k=0
    for a in range(ini,ini+tam-3,4):
        p=struct.unpack_from('<I',d,a)[0]
        c=(KEY[k]+((p^M)-M))&0xffffffff
        struct.pack_into('<I',o,a,c);k=(k+1)%per
    return bytes(o)
def chk(d,ini,tam): return sum(struct.unpack_from('<I',d,a)[0] for a in range(ini,ini+tam-3,4))&0xffffffff
def abrir(d):
    for ini,tam in BL[1:]: d=dec(d,ini,tam)
    return d
def fechar(d):
    d=bytearray(d)
    for ini,tam in BL[1:]: d=bytearray(enc(bytes(d),ini,tam))
    for ini,tam in BL: struct.pack_into('<I',d,ini-8,chk(bytes(d),ini,tam))
    return bytes(d)

# ---- mapa do Option File decifrado (offsets absolutos, arquivo decifrado) ----
JOG0=0x8770; NJOG=4880        # jogadores: 124 bytes, nome UTF-16LE 32 bytes no início
EDIT0=0x2e44                  # 184 jogadores editados (ids a partir de 32768)
TIMES_NOME=0xb26f8; NTIMES=130  # 88 bytes por time, nome latin1 no início
SLOT32=0x9ec10                # 130 times x 32 slots u16 (id jogador, 0=vaga), mesma ordem dos nomes
NUM32=0x9ce40                 # 130 x 32 bytes de número de camisa (255 = sem número)
def nome_jogador(p,i):
    b=p[JOG0+124*i:JOG0+124*i+32]
    for j in range(0,32,2):
        if b[j]==0 and b[j+1]==0: b=b[:j];break
    return b.decode('utf-16le','replace')
def nome_time(p,k): return p[TIMES_NOME+88*k:TIMES_NOME+88*k+48].split(b'\0')[0].decode('latin1')
def elenco(p,k): return [struct.unpack_from('<H',p,SLOT32+64*k+2*j)[0] for j in range(32)]
