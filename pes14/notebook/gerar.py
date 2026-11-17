import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhos import BASE, PUBLICAR
import json,sys,csv,shutil,os
from casar2 import *
def gerar(saida=BASE+'/novo'):
    orig=open(BASE+'/original/BESLES-556762014OPT/BESLES-556762014OPT','rb').read()
    d=bytearray(abrir(orig));pares=json.load(open(BASE+'/tm/pares.json'))
    S=lambda k,j:SLOT32+64*k+2*j; N=lambda k,j:NUM32+32*k+j
    gs=lambda k,j:struct.unpack_from('<H',d,S(k,j))[0]
    def tira(k,pid):
        for j in range(32):
            if gs(k,j)==pid:
                # preenche o buraco com o último jogador do elenco (mantém o prefixo denso)
                ult=max(x for x in range(32) if gs(k,x)) 
                struct.pack_into('<H',d,S(k,j),gs(k,ult));d[N(k,j)]=d[N(k,ult)]
                struct.pack_into('<H',d,S(k,ult),0);d[N(k,ult)]=255
                return True
        return False
    def poe(k,pid):
        for j in range(32):
            if gs(k,j)==0:
                struct.pack_into('<H',d,S(k,j),pid);d[N(k,j)]=255;return True
        return False
    log=[];feitos=0;fila=[]
    # 1ª passagem: tira quem sai (libera vagas)
    for v in pares.values():
        pid=v['jogo'];alvo=int(v['clube'])
        origens=[k for k in range(126) if pid in elenco(bytes(d),k)]
        if alvo in origens: continue
        for k in origens: tira(k,pid)
        fila.append((v,origens))
    # 2ª passagem: coloca quem chega
    for v,origens in fila:
        pid=v['jogo'];alvo=int(v['clube'])
        if poe(alvo,pid): feitos+=1;log.append(('OK',v['nome'],[nome_time(bytes(d),k) for k in origens],nome_time(bytes(d),alvo)))
        else:
            log.append(('CHEIO',v['nome'],nome_time(bytes(d),alvo)))
            for k in origens: poe(k,pid)   # sem vaga: volta ao clube antigo
    novo=fechar(bytes(d))
    os.makedirs(saida,exist_ok=True)
    for f in ('icon.sys','icon_view'): shutil.copy(f'{BASE}/original/BESLES-556762014OPT/{f}',saida)
    open(saida+'/BESLES-556762014OPT','wb').write(novo)
    return novo,log,feitos
if __name__=='__main__':
    novo,log,n=gerar();print('movidos',n,'tamanho',len(novo))
    print([l for l in log if l[0]!='OK'])
    json.dump(log,open(BASE+'/log_geracao.json','w'),ensure_ascii=False)
