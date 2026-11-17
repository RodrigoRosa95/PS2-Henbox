import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import sys;from casar2 import *
FREQ=collections.Counter(tok for g in G for tok in set(g))
def cand(j):
    t=norm(j['nome']);res=[]
    if not t: return res
    for i,g in enumerate(G):
        if not g: continue
        s=0
        if g==t: s=4
        elif len(g)>=2 and len(g[0])==1 and g[0]==t[0][0] and g[1:]==t[-len(g[1:]):] : s=3
        elif len(g)>=2 and g==t[-len(g):]: s=3
        elif len(g)==1 and len(g[0])>=4 and (g[0]==t[-1] or (len(t)==1 and g[0]==t[0])) : s=2 if (FREQ[g[0]]<=3 or len(t)==1) else 0   # só um nome (sobrenome ou apelido)
        elif len(g)==1 and len(g[0])>=4 and g[0] in t[1:-1]: s=1
        if not s: continue
        h=j['alt']
        if h is not None and abs(altura(i)-h)>2: continue   # altura incompatível -> descarta
        if j.get('nasc') and not (2013<=j['nasc']+idade(i)<=2017): continue   # ano de nascimento incompatível
        res.append((s,i))
    if not res: return []
    m=max(s for s,_ in res); return [i for s,i in res if s==m],m
def casar():
    pares={};stat=collections.Counter();usado=collections.defaultdict(list)
    for k,c in E2.items():
        for j in c['jogadores']:
            r=cand(j)
            if not r: stat['sem']+=1;continue
            ids,s=r
            if len(ids)>1:
                stat['ambiguo']+=1;continue
            if s<=1: stat['fraco']+=1;continue
            usado[ids[0]].append((k,j))
    for i,l in usado.items():
        if len(l)>1: stat['conflito']+=1;continue
        k,j=l[0];pares[j['id']]={'jogo':i,'clube':k,'nome':j['nome'],'nome_jogo':nome_jogador(p,i),'forca':cand(j)[1]};stat['ok']+=1
    return pares,stat
if __name__=='__main__':
    pares,stat=casar();print(stat)
    json.dump(pares,open(BASE+'/tm/pares.json','w'),ensure_ascii=False)
    import random;random.seed(1)
    for v in random.sample(list(pares.values()),25): print(v['nome'],'=>',v['nome_jogo'],v['forca'],'| 2017:',[nome_time(p,t)[:12] for t in atual.get(v['jogo'],[])],'-> hoje',nome_time(p,int(v['clube']))[:12])
