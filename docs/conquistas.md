# 🏆 Conquistas RetroAchievements no PS2 real

O PS2 Henbox liga o PS2 ao [RetroAchievements](https://retroachievements.org) usando o
[xeRAbora](https://github.com/hacan359/xerabora) (de hacan359): o PS2 roda o jogo e manda a memória dele pela rede; o
app xeRAbora, **rodando na própria TV box Android**, confere as conquistas e registra no seu perfil. O que o PS2
Henbox acrescenta é tirar o trabalho manual do caminho: **ninguém precisa abrir o menu do OPL para preparar jogo**.

## Como funciona

1. **Preparação automática (sem o PS2).** O `videos.py` da TV box confere os ISOs do pendrive dela a cada 30 minutos:
   - `ra_hash.py` calcula o hash RetroAchievements do ISO — o mesmo do `rc_hash_ps2` do
     [rcheevos](https://github.com/RetroAchievements/rcheevos): MD5 do nome do executável de boot (`BOOT2` do
     `SYSTEM.CNF`) seguido do conteúdo dele;
   - `ra_preparar.py` pede a lista de endereços ao app xeRAbora com o mesmo protocolo que o console usa
     (UDP 18194: `RAQ1` / `RAA1` / `RAG1` / `RAC1`) e grava `ps2/ra/<código>.wl` — os mesmos bytes que o OPL-RA
     grava no "RA: check game support";
   - o jogo entra no índice (`ps2/ra/indice.json`) com o ID dele no RetroAchievements; ISO não reconhecido é
     conferido de novo só uma vez por semana.
2. **As listas vão sozinhas para o PS2.** Quando o navegador conecta, o `navegador_servidor.py` copia os `.wl` novos
   para `mass:/RA/` no pendrive do PS2, onde o OPL-RA procura primeiro.
3. **Jogar.** Na Loja, **⬇ Copiar para o PS2** leva o ISO para `mass:/DVD/` (no fim a TV fala "Sua cópia foi concluída."); depois, **💾 No pendrive do PS2 → ▶ Jogar** (ou **🏆 Jogar com conquistas** na Loja) abre o
   [OPL-RA do Henbox](../conquistas/opl-ra/) direto no jogo, sem menu, pelo pendrive do PS2.
4. **Acompanhar.** A página **🏆 Conquistas** do navegador mostra o perfil e os pontos, o jogo atual, as conquistas
   desbloqueadas na partida e, por jogo, a lista com as medalhas (coloridas quando desbloqueadas). As medalhas vêm do
   site do RetroAchievements uma vez e ficam guardadas na TV box.

## O que precisa

- O app **xeRAbora** (`xerabora-android.apk`, das [releases](https://github.com/hacan359/xerabora/releases)) na TV box,
  com login e a Web API key do RetroAchievements. Para mantê-lo sempre ativo sem abrir a tela, o motor dele pode ser
  religado como root: `am start-foreground-service -n io.github.hacan359.xerabora/.EngineService`.
- O jogo **no pendrive do próprio PS2** — pelo Samba (rede) o xeRAbora ainda trava com tela preta
  ([issue #9](https://github.com/hacan359/xerabora/issues/9)).
- Um ISO que o RetroAchievements reconheça (cópia igual à cadastrada lá). Jogos com modo online podem não funcionar
  com a telemetria.

## Testado

Black (SLUS_213.76) no PS2 real, aberto pelo navegador a partir do pendrive do PS2: lista com 51 endereços,
**3.600 leituras completas por minuto (60 por segundo), nenhuma incompleta**, as 56 conquistas acompanhadas pelo
xeRAbora na TV box.
