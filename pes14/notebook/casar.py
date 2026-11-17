import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import json,re,unicodedata,sys,collections
from pes14fmt import *
p=open(BASE+'/opcao_decifrada.bin','rb').read()
def norm(s):
    s=s.replace('ø','o').replace('Ø','O').replace('ß','ss').replace('ł','l').replace('Ł','L').replace('đ','d').replace('æ','ae')
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().upper()
    return re.sub(r'[^A-Z0-9 ]',' ',s).split()
G=[norm(nome_jogador(p,i)) for i in range(NJOG)]
# time atual (2017) de cada jogador do jogo
atual={}
for k in range(NTIMES):
    for j in elenco(p,k):
        if j: atual.setdefault(j,[]).append(k)
def candidatos(tm_nome):
    t=norm(tm_nome)
    if not t: return []
    res=[]
    for i,g in enumerate(G):
        if not g: continue
        if g==t: res.append((3,i));continue            # nome completo igual
        # abreviado: "D RICE" ~ Declan Rice
        if len(g)>=2 and len(g[0])==1 and g[1:]==t[-len(g[1:]):] and g[0]==t[0][0]: res.append((2,i));continue
        # só sobrenome igual (jogo usa só sobrenome / apelido)
        if len(g)==1 and (g[0]==t[-1] or g[0]==t[0] or g[0] in t) and len(g[0])>=4: res.append((1,i));continue
        if len(g)>=2 and g==t[-len(g):] : res.append((2,i))
    if not res: return []
    m=max(s for s,_ in res)
    return [i for s,i in res if s==m],m
if __name__=='__main__':
    E=json.load(open(BASE+'/tm/elencos.json'))
    st=collections.Counter();log=[]
    for k,c in E.items():
        for j in c['jogadores']:
            r=candidatos(j['nome'])
            if not r: st['sem']+=1;continue
            ids,sc=r
            st['unico' if len(ids)==1 else 'ambiguo']+=1
    print(st)
