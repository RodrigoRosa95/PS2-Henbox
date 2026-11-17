import re,os,sys,shutil,json,urllib.request,tempfile,hashlib
AQUI=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(AQUI,'..','box'))
sys.path.insert(0,os.path.join(AQUI,'..','notebook'))
from caminhos import BASE, PUBLICAR
import pes14
ORIG=BASE+'/original/BESLES-556762014OPT'
SAVE='BESLES-556762014OPT'
class FakePS2:
    def __init__(s,raiz,falha_gravacao=False,sem_save=False):
        s.raiz=raiz;s.host=os.path.join(raiz,'host');s.mc=os.path.join(raiz,'mc0');s.aberto_=True;s.falha=falha_gravacao
        os.makedirs(s.host);os.makedirs(os.path.join(s.mc,SAVE) if not sem_save else s.mc)
        if not sem_save:
            for f in os.listdir(ORIG): shutil.copy(os.path.join(ORIG,f),os.path.join(s.mc,SAVE,f))
        s.escritas=[]
    def mapa(s,p):
        if p.startswith('host:'): return os.path.join(s.host,p[5:])
        for c in ('mc0','mc1'):
            if p.startswith(c+':/'): return os.path.join(s.raiz,c,p[len(c)+2:]) if c=='mc0' else None
        return None
    def op(s,n,o,d='-',tam=0):
        if n==8:
            m=s.mapa(o)
            if not m or not os.path.isdir(m): return False
            with open(s.mapa(d),'w') as f:
                for x in sorted(os.listdir(m)):
                    p=os.path.join(m,x);f.write(('D' if os.path.isdir(p) else 'F')+f'\t{x}\t{os.path.getsize(p)}\t2026-11-17\n')
            return True
        if n==0:
            a,b=s.mapa(o),s.mapa(d)
            if not a or not b or not os.path.isfile(a): return False
            os.makedirs(os.path.dirname(b),exist_ok=True)
            dados=open(a,'rb').read()
            if b.startswith(s.mc) and s.falha: dados=dados[:-1]+bytes([dados[-1]^1]) if o.startswith('host:pes14/novo') else dados  # grava corrompido
            open(b,'wb').write(dados);s.escritas.append((o,d));return True
        return False
def run(nome,fake_kw={},buscar=None):
    t=tempfile.mkdtemp()
    p=FakePS2(t,**fake_kw)
    def b(c): return open(PUBLICAR+c[len('/pes14'):],'rb').read()   # o que o servidor HTTP serviria em /pes14/
    a=pes14.Atualizador(p.op,p.host,lambda:p.aberto_,buscar or b,log=lambda *x:None,progresso=lambda t,c:a.vistos.append((t,c)))
    a.vistos=[]
    return p,a
sha=lambda c:hashlib.sha256(open(c,'rb').read()).hexdigest()
alvo=lambda p:os.path.join(p.mc,SAVE,SAVE)
orig_sha=sha(ORIG+'/'+SAVE)
man=json.load(open(PUBLICAR+'/manifest.json'))
# 1 caminho feliz
p,a=run('feliz');ok,msg=a.rodar();print('1 feliz:',ok,msg[:70]);assert ok and sha(alvo(p))==man['arquivos'][0]['sha256']
assert any(os.path.isfile(os.path.join(p.host,'pes14','backup',d,SAVE)) and sha(os.path.join(p.host,'pes14','backup',d,SAVE))==orig_sha for d in os.listdir(os.path.join(p.host,'pes14','backup')))
for f in ('icon.sys','icon_view'): assert sha(os.path.join(p.mc,SAVE,f))==sha(ORIG+'/'+f)   # ícones intocados
v=a.vistos;pc=[c for _,c in v];print('  progresso:',len(v),'marcas, de',pc[0],'a',pc[-1],'| etapas:',sorted({re.sub(r' \d+s$','',t) for t,_ in v}));assert pc[-1]==100 and all(0<=c<=100 for c in pc) and pc==sorted(pc)
# 2 já atualizado
ok,msg=a.rodar();print('2 repetir:',ok,msg);assert ok and 'Já está' in msg
# 3 desfazer
ok,msg=a.desfazer();print('3 desfazer:',ok,msg[:60]);assert ok and sha(alvo(p))==orig_sha
# 4 gravação corrompida -> volta o backup
p,a=run('falha',{'falha_gravacao':True});ok,msg=a.rodar();print('4 falha:',ok,msg[:110]);assert not ok and sha(alvo(p))==orig_sha
# 5 arquivo corrompido vindo do notebook
def ruim(c):
    d=open(PUBLICAR+c[len('/pes14'):],'rb').read()
    return d[:5000]+bytes([d[5000]^0xFF])+d[5001:] if c.endswith(SAVE) and 'manifest' not in c else d
p,a=run('ruim',buscar=ruim);ok,msg=a.rodar();print('5 download ruim:',ok,msg[:80]);assert not ok and sha(alvo(p))==orig_sha and not p.escritas
# 6 sem save no cartão
p,a=run('sem',{'sem_save':True});ok,msg=a.rodar();print('6 sem save:',ok,msg[:70]);assert not ok and not p.escritas
# 7 navegador fecha no meio
p,a=run('fecha');orig=p.op
def op2(n,o,d='-',t=0):
    r=orig(n,o,d,t)
    if n==0 and o.startswith('host:pes14/novo'): p.aberto_=False
    return r
a.op_ps2=op2;ok,msg=a.rodar();print('7 fecha:',ok,msg[:70]);assert not ok
print('TODOS OS TESTES OK')
