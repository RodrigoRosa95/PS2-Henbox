import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import json,re,sys,collections,unicodedata
from pes14fmt import *
from casar import norm,G,atual,p
def u16(o): return struct.unpack_from('<H',p,o)[0]
def reg(i): return JOG0+124*i
def altura(i): return (u16(reg(i)+88)&0x3F)+148
def idade(i): return ((u16(reg(i)+112)>>9)&0x1F)+15
def nacao(i): return u16(reg(i)+112)&0x7F
E2=json.load(open(BASE+'/tm/elencos2.json'))
if __name__=='__main__':
    for n in ('COURTOIS','MESSI','NEYMAR JR','C. RONALDO'):
        i=[x for x in range(NJOG) if ' '.join(G[x])==n][0];print(n,i,altura(i),idade(i),nacao(i))
