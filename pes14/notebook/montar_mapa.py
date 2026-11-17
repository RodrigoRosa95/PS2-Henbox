import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import json,html
auto=json.load(open(BASE+'/tm/mapa_auto.json'))
bus=json.load(open(BASE+'/tm/busca.json'))
ov={'25':'Botafogo de Futebol e Regatas','27':'Sport Club do Recife','31':'Grêmio Foot-Ball Porto Alegrense','35':'Esporte Clube Vitória'}
fix={'50':('SPAL','spal','2722'),'82':('Deportivo A Coruña','deportivo-la-coruna','897'),'118':('Santa Cruz FC (PE)','santa-cruz-futebol-clube-pe-','1785'),'123':('Paysandu SC','paysandu-sport-club-pa-','6347'),'124':('Figueirense Futebol Clube','figueirense-fc','4064')}
LG=json.load(open(BASE+'/tm/ligas.json'))
SKIP={'126','127','128','129'}  # times fictícios/all-stars
mapa={}
for k,(g,c) in auto.items():
    if k in SKIP: continue
    if k in fix: t=fix[k]
    elif k in ov: t=next((x,s_,i) for l in LG.values() for x,s_,i in l if x==ov[k])
    elif c and len(c)==1: t=c[0][:3]
    elif k in bus: t=bus[k][0]
    else: t=None
    if t: mapa[k]={'jogo':g,'tm':html.unescape(t[0]),'slug':t[1],'id':t[2]}
    else: print('SEM',k,g,c)
json.dump(mapa,open(BASE+'/tm/mapa_clubes.json','w'),ensure_ascii=False,indent=0)
print(len(mapa))
for k,v in mapa.items(): print(k,v['jogo'],'=>',v['tm'])
