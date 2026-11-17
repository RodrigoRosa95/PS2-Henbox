import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import json,re,subprocess,time,urllib.parse,sys
UA="Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
def get(u):
    return subprocess.run(['curl','-s','-m30','-A',UA,'-H','Accept-Language: en-US,en;q=0.9',u],capture_output=True,text=True,errors='ignore').stdout
def buscar_clube(q):
    h=get('https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query='+urllib.parse.quote(q)+'&Verein_page=1')
    ms=re.findall(r'<td class="hauptlink">\s*<a title="([^"]+)" href="/([^/]+)/startseite/verein/(\d+)"',h)
    return ms[:4]
if __name__=='__main__':
    Q={6:'Leicester City',7:'Watford',11:'Burnley',12:'Brighton',13:'Southampton',14:'Stoke City',15:'Huddersfield Town',16:'Swansea City',18:'West Bromwich Albion',19:'West Ham United',32:'Athletico Paranaense',36:'Atlético Goianiense',39:'Atlético Mineiro',41:'Benevento',44:'Chievo',50:'SPAL',53:'Crotone',55:'Sampdoria',59:'Hellas Verona',60:'FC Augsburg',65:'1.FC Köln',70:'Hertha BSC',73:'Hannover 96',77:'VfL Wolfsburg',84:'UD Las Palmas',86:'Deportivo Alavés',87:'Girona FC',90:'SD Eibar',91:'CD Leganés',100:'BATE Borisov',106:'Olympiacos Piraeus',107:'PAOK',108:'FC Basel',117:'Ludogorets',118:'Santa Cruz FC',120:'Brasil de Pelotas',123:'Paysandu',124:'Figueirense',82:'Deportivo La Coruña'}
    out={}
    for k,q in Q.items():
        out[k]=buscar_clube(q);print(k,q,'->',out[k][:2]);time.sleep(2)
    json.dump(out,open(BASE+'/tm/busca.json','w'),ensure_ascii=False)
