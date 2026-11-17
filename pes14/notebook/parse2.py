import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import re,json,html
D=BASE+'/tm/'
mapa=json.load(open(D+'mapa_clubes.json'));out={}
for k,c in mapa.items():
    try: h=re.sub(r'\s+',' ',open(D+f'elencos/{k}.html',errors='ignore').read())
    except: continue
    partes=h.split('rueckennummer')[1:]
    js=[]
    for s in partes:
        a=re.search(r'href="/([^/"]+)/profil/spieler/(\d+)">\s*([^<]+?)\s*</a>',s)
        if not a: continue
        pos=re.search(r'title="([^"]+)"',s[:120])
        dob=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4}) \((\d+)\)',s)
        nac=re.findall(r'title="([^"]+)" alt="[^"]*" class="flaggenrahmen"',s)
        alt=re.search(r'(\d),(\d\d)m',s)
        js.append({'id':a.group(2),'nome':html.unescape(a.group(3)),'pos':pos.group(1) if pos else '',
          'nasc':int(dob.group(3)) if dob else None,'idade':int(dob.group(4)) if dob else None,
          'nac':list(dict.fromkeys(nac)),'alt':int(alt.group(1))*100+int(alt.group(2)) if alt else None})
    out[k]={'clube':c['tm'],'jogadores':js}
json.dump(out,open(D+'elencos2.json','w'),ensure_ascii=False)
n=sum(len(v['jogadores']) for v in out.values());print(n,sum(1 for v in out.values() for j in v['jogadores'] if j['alt'] and j['nac'] and j['nasc']))
print(out['92']['jogadores'][0])
