/*
 * Modo vídeo do navegador do PS2 (pedido do usuário 17/10/2026: Jellyfin e TV ao vivo no PS2).
 * Incluído em navegador.c (usa gs, tela, controle, escrever_entrada...).
 *
 * O notebook (cinema.py) converte para:  host:video/<sessão>.m2v  MPEG-2 elementar 640x400 ~30 fps (no máximo 1023
 *                                         macroblocos: acima disso o CSC em duas partes do libmpeg do ps2sdk trava)
 *                                         host:video/<sessão>.pcm  PCM 16 bits estéreo 22050 Hz
 *                                         host:video/<sessão>.fim  existe quando a conversão acabou
 * Os arquivos crescem enquanto o PS2 toca. Duas threads leem pelo host: do PS2Link (vídeo para um anel na RAM,
 * áudio direto para o audsrv); o laço principal decodifica no IPU (libmpeg) e manda cada quadro por DMA para a
 * textura da tela. O relógio é o áudio: quadro k aparece quando o áudio tocado passa de k * ms_por_quadro.
 * Controle: O para, X/START pausa, ← → (o notebook recomeça 30 s para trás/frente e manda outra sessão).
 */
#include <libmpeg.h>
#include <dma.h>
#include <dma_tags.h>
#include <gif_tags.h>
#include <gs_gp.h>
#include <gs_psm.h>
#include <packet.h>

#define ANEL (4 * 1024 * 1024)            /* vídeo já baixado e ainda não decodificado */
#define BLOCO_IPU 2048
/* pré-carga: o decodificador só anda com folga no anel. A libmpeg chama ipu_dados também de dentro da interrupção
   do DMA (fim da conversão de cor), onde não dá para esperar; sem folga ela parava com o anel cheio e o áudio tocando. */
#define ANEL_BAIXO (256 * 1024)
#define ANEL_ALTO (1024 * 1024)

/* som_pausado, video_pedido, video_m2v/pcm/fim, video_pos_ms e video_ativo ficam em navegador.c (usados antes) */

static unsigned char *anel;
static int video_alt = ALT;   /* altura do vídeo; fica centralizado na tela */
static volatile unsigned int anel_escrito, anel_lido;   /* contadores absolutos (posição = % ANEL) */
static volatile int video_parar, video_eof_dados, video_pausa, video_carregando;
static volatile unsigned int audio_bytes;   /* bytes de áudio já entregues ao audsrv */
static u8 pilha_vleitor[16 * 1024] __attribute__((aligned(16)));
static u8 pilha_aleitor[16 * 1024] __attribute__((aligned(16)));
static int fim_existe(void) { int fd = open(video_fim, O_RDONLY); if (fd < 0) return 0; close(fd); return 1; }

static void thread_vleitor(void *arg)
{
    int fd = open(video_m2v, O_RDONLY), n, vazias = 0;
    (void)arg;
    while (!video_parar && fd >= 0) {
        unsigned int livre = ANEL - (anel_escrito - anel_lido), pos = anel_escrito % ANEL;
        unsigned int quer = 32768;
        if (livre < quer) { DelayThread(5000); continue; }
        if (quer > ANEL - pos) quer = ANEL - pos;
        n = read(fd, anel + pos, quer);
        if (n > 0) { SyncDCache(anel + pos, anel + pos + n); anel_escrito += n; vazias = 0; continue; }
        /* fim do que já foi convertido: espera mais, a não ser que a conversão tenha acabado */
        if (++vazias % 10 == 0 && fim_existe()) { n = read(fd, anel + pos, quer); if (n <= 0) break; anel_escrito += n; continue; }
        DelayThread(50000);
    }
    if (fd >= 0) close(fd);
    video_eof_dados = 1;
    ExitDeleteThread();
}

static void thread_aleitor(void *arg)
{
    static char buf[4096] __attribute__((aligned(64)));
    struct audsrv_fmt_t fmt = {22050, 16, 2};
    int fd = open(video_pcm, O_RDONLY), n, vazias = 0;
    (void)arg;
    audsrv_set_format(&fmt);
    while (!video_parar && fd >= 0) {
        if (video_pausa || video_carregando) { DelayThread(20000); continue; }
        n = read(fd, buf, sizeof(buf));
        if (n <= 0) {
            if (++vazias % 10 == 0 && fim_existe()) break;
            DelayThread(30000);
            continue;
        }
        vazias = 0;
        audsrv_wait_audio(n);
        audsrv_play_audio(buf, n);
        audio_bytes += n;
    }
    if (fd >= 0) close(fd);
    ExitDeleteThread();
}

/* EXL/ERL ligados = rodando dentro de uma interrupção (não pode chamar DelayThread nem outras chamadas do sistema) */
static int em_interrupcao(void)
{
    unsigned int st;
    __asm__ __volatile__("mfc0 %0, $12" : "=r"(st));
    return (st & 6) != 0;
}

/* libmpeg pede dados: manda 2048 bytes do anel para o IPU. Como no SMS: escreve direto nos registradores do canal 4
   (toIPU), sem libdma nem SyncDCache (o cache do anel já foi gravado pela thread de leitura). */
static int ipu_dados(void *u)
{
    unsigned char *p;
    (void)u;
    while (anel_escrito - anel_lido < BLOCO_IPU) {
        if (video_parar || video_eof_dados || em_interrupcao()) return 0;
        DelayThread(5000);
    }
    p = anel + anel_lido % ANEL;   /* ANEL é múltiplo de 2048: um bloco nunca passa da borda */
    *(volatile unsigned int *)0x1000B410 = (unsigned int)p & 0x1FFFFFFF;   /* D4_MADR */
    *(volatile unsigned int *)0x1000B420 = BLOCO_IPU >> 4;                 /* D4_QWC */
    *(volatile unsigned int *)0x1000B400 = 0x0101;                         /* D4_CHCR: memória → IPU, inicia */
    anel_lido += BLOCO_IPU;
    return 1;
}

typedef struct { MPEGSequenceInfo *info; void *dados; packet_t *envio; } VideoSeq;

/* nova sequência MPEG: área do quadro decodificado + pacote DMA que copia os blocos 16x16 para a textura "tela" */
static void *ipu_inicio(void *param, MPEGSequenceInfo *si)
{
    VideoSeq *vs = (VideoSeq *)param;
    int tam = si->m_Width * si->m_Height * 4, mbw = si->m_Width >> 4, mbh = si->m_Height >> 4;
    int tbw = (LARG + 63) >> 6, x, y;
    unsigned char *img;
    qword_t *q;
    if (vs->dados) free(vs->dados);
    if (vs->envio) packet_free(vs->envio);
    vs->dados = img = memalign(64, tam);
    vs->info = si;
    video_alt = si->m_Height < ALT ? si->m_Height : ALT;
    SyncDCache(img, img + tam);
    vs->envio = packet_init((10 + 12 * mbw * mbh) >> 1, PACKET_NORMAL);
    q = vs->envio->data;
    DMATAG_CNT(q, 3, 0, 0, 0); q++;
    PACK_GIFTAG(q, GIF_SET_TAG(2, 0, 0, 0, 0, 1), GIF_REG_AD); q++;
    PACK_GIFTAG(q, GS_SET_TRXREG(16, 16), GS_REG_TRXREG); q++;
    PACK_GIFTAG(q, GS_SET_BITBLTBUF(0, 0, 0, tela.Vram / 256, tbw, GS_PSM_32), GS_REG_BITBLTBUF); q++;
    for (y = 0; y < si->m_Height && y < ALT; y += 16)
        for (x = 0; x < si->m_Width; x += 16, img += 1024) {
            if (x >= LARG) continue;
            DMATAG_CNT(q, 4, 0, 0, 0); q++;
            PACK_GIFTAG(q, GIF_SET_TAG(2, 0, 0, 0, 0, 1), GIF_REG_AD); q++;
            PACK_GIFTAG(q, GS_SET_TRXPOS(0, 0, x, y, 0), GS_REG_TRXPOS); q++;
            PACK_GIFTAG(q, GS_SET_TRXDIR(0), GS_REG_TRXDIR); q++;
            PACK_GIFTAG(q, GIF_SET_TAG(64, 1, 0, 0, 2, 0), 0); q++;
            DMATAG_REF(q, 64, (unsigned)img, 0, 0, 0); q++;
        }
    DMATAG_END(q, 0, 0, 0, 0); q++;
    vs->envio->qwc = q - vs->envio->data;
    return vs->dados;
}

static unsigned short video_botoes(void)
{
    struct padButtonStatus pad;
    unsigned short b = 0;
    if (padRead(0, 0, &pad) != 0) b = 0xFFFF ^ pad.btns;
    if (ds34bt_get_status(0) & DS34BT_STATE_RUNNING) {
        struct padButtonStatus bt;
        memset(&bt, 0, sizeof(bt));
        if (ds34bt_get_data(0, (u8 *)&bt.btns) != 0) b |= 0xFFFF ^ bt.btns;
    }
    return b;
}

static void video_quadro(int barra, int pausado)
{
    gsKit_clear(gs, GS_SETREG_RGBAQ(0, 0, 0, 0x80, 0));
    {
        int y0 = (ALT - video_alt) / 2;
        gsKit_prim_sprite_texture(gs, &tela, 0, y0, 0, 0, LARG, y0 + video_alt, LARG, video_alt, 1,
                                  GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0));
    }
    if (pausado) {   /* símbolo de pausa */
        gsKit_prim_sprite(gs, 290, 190, 310, 250, 2, GS_SETREG_RGBAQ(0xFF, 0xFF, 0xFF, 0x80, 0));
        gsKit_prim_sprite(gs, 330, 190, 350, 250, 2, GS_SETREG_RGBAQ(0xFF, 0xFF, 0xFF, 0x80, 0));
    }
    if (barra > 0) gsKit_prim_sprite(gs, 0, ALT - 4, barra, ALT, 2, GS_SETREG_RGBAQ(0x40, 0x80, 0xFF, 0x80, 0));
    gsKit_queue_exec(gs);
    gsKit_sync_flip(gs);
}

/* Toca a sessão pedida. Volta quando acaba, quando o usuário aperta O ou quando chega outra sessão (← →).
   Devolve 9 = acabou, 10 = parado pelo usuário, 11 = trocou de sessão. */
static int tocar_video(void)
{
    VideoSeq vs = {0, 0, 0};
    ee_thread_t t;
    s64 pts, pts_atual;
    unsigned int quadro_n = 0, antes = 0xFFFF;
    int ms_quadro = 33, resultado = 9, tid;

    if (!anel) anel = memalign(64, ANEL);
    anel_escrito = anel_lido = 0;
    video_parar = video_eof_dados = video_pausa = 0;
    video_carregando = 1;   /* começa enchendo o anel */
    audio_bytes = 0;
    video_pos_ms = 0;
    video_ativo = 1;
    som_pausado = 1;
    video_pedido = 0;

    memset(&t, 0, sizeof(t));
    t.func = thread_vleitor; t.stack = pilha_vleitor; t.stack_size = sizeof(pilha_vleitor);
    t.gp_reg = &_gp; t.initial_priority = 0x48;
    if ((tid = CreateThread(&t)) >= 0) StartThread(tid, NULL);
    t.func = thread_aleitor; t.stack = pilha_aleitor; t.stack_size = sizeof(pilha_aleitor);
    t.initial_priority = 0x44;
    if ((tid = CreateThread(&t)) >= 0) StartThread(tid, NULL);

    MPEG_Initialize(ipu_dados, NULL, ipu_inicio, &vs, &pts_atual);
    for (;;) {
        unsigned short b = video_botoes();
        unsigned short novo = b & ~antes;
        antes = b;
        in_botoes = b;   /* a thread de rede manda ao notebook (← → recomeçam a conversão lá) */
        if (novo & PAD_CIRCLE) { resultado = 10; break; }
        if (video_pedido) { resultado = 11; break; }
        if (pedido_sair) { resultado = 10; break; }   /* "sair" do notebook também encerra o vídeo */
        if (novo & (PAD_CROSS | PAD_START)) video_pausa = !video_pausa;
        if (video_pausa) { video_quadro(0, 1); continue; }
        {   /* pouco vídeo no anel: espera encher (o áudio também espera, para não perder a sincronia) */
            unsigned int tem = anel_escrito - anel_lido;
            if (!video_eof_dados && (tem < ANEL_BAIXO || (video_carregando && tem < ANEL_ALTO))) {
                video_carregando = 1;
                video_quadro(1 + (int)((unsigned long long)tem * LARG / ANEL_ALTO), 0);
                continue;
            }
            video_carregando = 0;
        }

        if (!MPEG_Picture(vs.dados, &pts)) break;   /* fim da sequência ou dos dados */
        if (vs.info && vs.info->m_MSPerFrame > 0) ms_quadro = vs.info->m_MSPerFrame;
        quadro_n++;
        video_pos_ms = (int)((unsigned long long)audio_bytes * 1000 / (22050 * 4));
        /* relógio do áudio: espera se o vídeo está adiantado; pula a exibição se está muito atrasado */
        if ((int)(quadro_n * ms_quadro) > video_pos_ms + 120 && !video_eof_dados) {
            int espera = 0;
            while ((int)(quadro_n * ms_quadro) > (int)((unsigned long long)audio_bytes * 1000 / (22050 * 4)) + 40 &&
                   espera++ < 30 && !video_parar)
                gsKit_vsync_wait();
        } else if ((int)(quadro_n * ms_quadro) + 250 < video_pos_ms) {
            continue;   /* atrasado: não mostra este quadro */
        }
        dma_channel_wait(DMA_CHANNEL_GIF, 0);
        dma_channel_send_chain(DMA_CHANNEL_GIF, vs.envio->data, vs.envio->qwc, 0, 0);
        dma_channel_wait(DMA_CHANNEL_GIF, 0);
        video_quadro(0, 0);
    }
    video_parar = 1;
    MPEG_Destroy();
    DelayThread(200000);   /* as threads de leitura percebem o video_parar e saem */
    audsrv_stop_audio();
    {   /* volta o formato do som da interface (mono 22050) */
        struct audsrv_fmt_t fmt = {SOM_HZ, 16, 1};
        audsrv_set_format(&fmt);
    }
    if (vs.dados) free(vs.dados);
    if (vs.envio) packet_free(vs.envio);
    som_pausado = 0;
    video_ativo = 0;
    sujo = 1;   /* a textura tem o último quadro do vídeo: redesenha a página */
    return resultado;
}
