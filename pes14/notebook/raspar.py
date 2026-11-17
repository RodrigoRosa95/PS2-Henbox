import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import json,re,subprocess,time,html,os
UA="Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
D=BASE+'/tm/'
mapa=json.load(open(D+'mapa_clubes.json'))
os.makedirs(D+'elencos',exist_ok=True)
out=json.load(open(D+'elencos.json')) if os.path.exists(D+'elencos.json') else {}
for k,c in mapa.items():
    if k in out and out[k]['jogadores']: continue
    u=f"https://www.transfermarkt.com/{c['slug']}/kader/verein/{c['id']}/plus/1"
    h=subprocess.run(['curl','-s','-m40','-A',UA,'-H','Accept-Language: en-US,en;q=0.9',u],capture_output=True,text=True,errors='ignore').stdout
    open(D+f'elencos/{k}.html','w').write(h)
    js=[]
    for m in re.finditer(r'<tr class="(?:odd|even)">(.*?)</tr>\s*(?=<tr class="(?:odd|even)">|</tbody>)',h,re.S):
        r=m.group(1)
        a=re.search(r'<td class="hauptlink">\s*<a href="/([^/]+)/profil/spieler/(\d+)">\s*([^<]+?)\s*</a>',r)
        if not a: continue
        pos=re.search(r'<td>([A-Za-z -]{4,25})</td>\s*</tr>\s*</table>',r) or re.search(r'title="([^"]*)"\s*class="[^"]*"',r)
        js.append({'slug':a.group(1),'id':a.group(2),'nome':html.unescape(a.group(3))})
    out[k]={'clube':c['tm'],'jogadores':js}
    json.dump(out,open(D+'elencos.json','w'),ensure_ascii=False)
    print(k,c['tm'],len(js),flush=True)
    time.sleep(3)
