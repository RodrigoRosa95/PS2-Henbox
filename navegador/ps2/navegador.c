/*
 * Navegador do PS2 (pedido do usuário 16/10/2026): cliente "magro" de um navegador que roda no notebook.
 * O notebook (navegador_servidor.py) abre a página num Chromium sem janela; este .elf só mostra a imagem,
 * desenha o cursor e devolve o controle.
 *
 * Transporte: arquivos pelo host: do PS2Link (o ps2client fica servindo a pasta ps2/ do notebook enquanto o
 * programa roda). Duas tentativas com rede própria falharam neste PS2 (pilha no EE: dados estragados; pilha no
 * IOP via ps2ips: recv travava) — ficaram em navegador.c.ee-lwip e navegador.c.iop-socket. O host: do PS2Link
 * é o mesmo canal que carrega o Neutrino e os módulos dele, comprovado. Por isso o IOP NÃO é reiniciado na entrada.
 *
 * Arquivos (little-endian):
 *   host:dif.bin       "PST2" seq:u32 base:u32 cmd:u32 tam:u32 + registros  (mudanças de base → seq)
 *   host:completa.bin  idem com base 0 (tela inteira)
 *     registro: "PSF2" x:u16 y:u16 w:u16 h:u16 tam:u32 crc:u32 + zlib(w*h*4 bytes RGBX)
 *     cmd 1 = sair (o notebook precisa do PS2Link, ex.: "Alexa, abrir GTA")
 *     cmd: byte baixo 1 = sair; bit 0x100 = tocar a música de fundo (a loja liga)
 *   host:entrada.bin   escrito pelo PS2: "PSI2" botoes:u16 (1 = apertado) cx:u16 cy:u16 rx:i8 ry:i8 seq:u32
 *                      teclas:u16 (contador) roda:i8 0 + 64 bytes (últimas teclas, posição = contador % 64) = 84 bytes
 *                      teclas: ASCII; 0x80|código para as especiais do teclado USB (setas, Delete...)
 *     cmd bit 0x200 = há pedido de cópia em host:pedido.bin
 *   host:pedido.bin    "PSP1" id:u32 tam:u32 origem[128] destino[128] op:u32   (op 0 = copiar, ex.: host:snes/X.smc →
 *                      mass:/SNES/X.smc; op 1 = executar: origem = ELF no pendrive, destino = argumento, ex.: RetroArch
 *                      mass:/APPS/RETROARCH/snes9x2002_libretro_ps2.elf com a ROM mass:/SNES/X.smc)
 *   entrada.bin bytes 84..91: pedido_id:u32 estado:u8 pct:u8 usb:u8 0   (estado 1 copiando, 2 pronto,
 *                      3 sem driver USB, 4 erro lendo origem, 5 pendrive ausente/erro ao criar, 6 erro gravando,
 *                      7 abrindo o programa do pendrive)
 *     op 2 = tocar vídeo: origem = host:video/<sessão>.m2v, destino = host:video/<sessão>.pcm (video.inc.c)
 *     op 3 = apagar origem do pendrive; a cópia (op 0) roda numa thread própria (a tela não para)
 *   entrada.bin bytes 91..95: vídeo ativo:u8 posição_ms:u32   (estado 8 tocando, 9 acabou, 10 parado)
 *   host:clique.raw / host:musica.raw   sons PCM 16 bits mono 22050 Hz (gerados no notebook)
 *   host:temperatura.txt   escrito pelo PS2 a cada 10 s: °C do sensor do Mechacon ("41.5"), ver temperatura.py
 * Controle: o com fio (porta 1) e o DualShock 4/3 por Bluetooth no adaptador USB, com o mesmo driver e o mesmo
 * pareamento do OPL (o DS4 guarda o endereço do adaptador; no OPL: $EnablePadEmu=1, $PadEmuSettings=257).
 * Mouse e teclado USB: mouse move o cursor (esquerdo = X, direito = O, rodinha rola); teclado digita.
 * Som (audsrv): clique ao apertar X/mouse e música de fundo quando o notebook pede (loja).
 * SELECT+START sai. Ao sair volta para o PS2Link do memory card (mc1:/APPS/PS2LINK) pelo elf-loader.
 *
 * Rede própria (17/10/2026): aberto pelo OPL (argv[0] fora do host:, ex.: mass:/APPS/NAVEGADOR/navegador.elf), o
 * navegador reinicia o IOP e liga a mesma pilha do PS2Link (ps2dev9 + netman + smap + ps2ip-nm, IP fixo
 * 192.168.4.230, ou ip=/mascara=/gw= nos argumentos) e o navlink.irx: o servidor host: do PS2Link na porta 0x4721.
 * O notebook (navegador/servidor_host.py) conecta e serve a mesma pasta ps2/, então todo o resto (arquivos acima,
 * vídeo, cópias) funciona igual, sem PS2Link nem ps2client.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include <kernel.h>
#include <iopcontrol.h>
#include <iopheap.h>
#include <sifrpc.h>
#include <loadfile.h>
#include <startup.h>
#include <sbv_patches.h>
#include <fcntl.h>
extern void fioExit(void);   /* (fileio.h não pode ser incluído no newlib) religa o fio depois de reiniciar o IOP */
#include <unistd.h>
#include <libpad.h>
#include <gsKit.h>
#include <dmaKit.h>
#include <zlib.h>
#include <elf-loader.h>
#include <libmouse.h>
#include <libkbd.h>
#include <ps2kbd.h>
#include <audsrv.h>
#include <delaythread.h>
#include <libcdvd.h>
#include "opl-ds34bt/libds34bt.h"   /* DualShock 3/4 por Bluetooth, driver do OPL (opl-ds34bt/ORIGEM.txt) */

extern unsigned char USBD_irx[], DS34BT_irx[], MOUSE_irx[], KBD_irx[], LIBSD_irx[], AUDSRV_irx[];
extern unsigned int size_USBD_irx, size_DS34BT_irx, size_MOUSE_irx, size_KBD_irx, size_LIBSD_irx, size_AUDSRV_irx;
extern unsigned char IOMANX_irx[], BDM_irx[], BDMFS_irx[], USBMASS_irx[];
extern unsigned int size_IOMANX_irx, size_BDM_irx, size_BDMFS_irx, size_USBMASS_irx;
extern unsigned char DEV9_irx[], NETMAN_irx[], SMAP_irx[], PS2IP_irx[], NAVLINK_irx[];
extern unsigned int size_DEV9_irx, size_NETMAN_irx, size_SMAP_irx, size_PS2IP_irx, size_NAVLINK_irx;
extern unsigned char POWEROFF_irx[], UDPTTY_irx[], IOPTRAP_irx[];
extern unsigned int size_POWEROFF_irx, size_UDPTTY_irx, size_IOPTRAP_irx;

#define LARG 640
#define ALT 448
#define BUF_MAX (LARG * ALT * 4 + 64 * 1024)

static GSGLOBAL *gs;
static GSTEXTURE tela;
static u32 *quadro;                 /* LARG*ALT pixels RGBX (cópia na RAM do EE) */
static volatile int sujo = 1;
static char padBuf[256] __attribute__((aligned(64)));
static unsigned char *arq, *desc;   /* arquivo lido do notebook / retângulo descomprimido */
static unsigned int minha_seq = 0;
static unsigned char teclas[64];
static unsigned short n_teclas = 0;
static int roda = 0;                 /* rodinha do mouse acumulada até a próxima escrita */
/* cópia para o pendrive do PS2 (mass:) */
static volatile unsigned short in_botoes = 0;
static volatile int in_cx = LARG / 2, in_cy = ALT / 2, in_rx = 0, in_ry = 0, pedido_sair = 0;
static unsigned int pedido_id = 0, pedido_feito = 0;
static int pedido_pendente = 0;
static char exec_elf[129], exec_arg[129];   /* programa do pendrive para abrir ao sair (op 1) */
static unsigned char pedido_estado = 0, pedido_pct = 0, usb_carregado = 0;

/* ---------------- som ---------------- */
#define SOM_HZ 22050
static short *musica = NULL, *clique = NULL;
static int musica_n = 0, clique_n = 0, musica_pos = 0;
static volatile int musica_ligada = 0, clique_pos = -1;
/* modo vídeo (video.inc.c): pedido pelo notebook com op 2 em pedido.bin */
static volatile int som_pausado = 0;
/* Saída (Jogar/sair): as threads de som, rede e cópia param num ponto seguro antes do audsrv_quit e do
   LoadELFFromFile. Sem isso o PS2 real congelava ao sair (17/10/2026): elas seguiam chamando o IOP no reset. */
static volatile int parar_threads = 0, som_parado = 0, rede_parada = 0;
static int id_som = -1, id_rede = -1;      /* thread_som (música/clique) fica quieta durante o vídeo */
static volatile int video_pedido = 0;
static char video_m2v[129], video_pcm[129], video_fim[129];
static volatile int video_pos_ms = 0, video_ativo = 0;
static u8 pilha_som[16 * 1024] __attribute__((aligned(16)));

static short *carregar_som(const char *nome, int *amostras)
{
    int fd = open(nome, O_RDONLY), tam, n, total = 0;
    short *b;
    if (fd < 0) return NULL;
    tam = lseek(fd, 0, SEEK_END);
    lseek(fd, 0, SEEK_SET);
    if (tam <= 0 || tam > 4 * 1024 * 1024 || !(b = memalign(64, tam))) { close(fd); return NULL; }
    while (total < tam && (n = read(fd, (char *)b + total, tam - total)) > 0) total += n;
    close(fd);
    *amostras = total / 2;
    return b;
}

static void thread_som(void *arg)
{
    static short bloco[512] __attribute__((aligned(64)));
    (void)arg;
    for (;;) {
        int i;
        if (parar_threads) { som_parado = 1; SleepThread(); }
        if (som_pausado) { DelayThread(10000); continue; }
        for (i = 0; i < 512; i++) {
            int v = 0;
            if (musica_ligada && musica_n) { v += musica[musica_pos] / 2; if (++musica_pos >= musica_n) musica_pos = 0; }
            if (clique_pos >= 0 && clique) { v += clique[clique_pos]; if (++clique_pos >= clique_n) clique_pos = -1; }
            bloco[i] = v > 32767 ? 32767 : (v < -32768 ? -32768 : v);
        }
        audsrv_wait_audio(sizeof(bloco));
        audsrv_play_audio((char *)bloco, sizeof(bloco));
    }
}

static void iniciar_som(void)
{
    struct audsrv_fmt_t fmt = {SOM_HZ, 16, 1};
    ee_thread_t t;
    int id;
    SifExecModuleBuffer(LIBSD_irx, size_LIBSD_irx, 0, NULL, NULL);
    SifExecModuleBuffer(AUDSRV_irx, size_AUDSRV_irx, 0, NULL, NULL);
    if (audsrv_init() != 0) return;
    audsrv_set_format(&fmt);
    audsrv_set_volume(MAX_VOLUME);
    clique = carregar_som("host:clique.raw", &clique_n);
    memset(&t, 0, sizeof(t));
    t.func = thread_som; t.stack = pilha_som; t.stack_size = sizeof(pilha_som);
    t.gp_reg = &_gp; t.initial_priority = 0x40;
    if ((id = CreateThread(&t)) >= 0) { StartThread(id, NULL); id_som = id; }
}

static unsigned int u32le(const unsigned char *p) { return p[0] | p[1] << 8 | p[2] << 16 | (unsigned)p[3] << 24; }
static unsigned int u16le(const unsigned char *p) { return p[0] | p[1] << 8; }

/* Lê um arquivo de tela do host: para arq. Primeiro só o cabeçalho (20 bytes): se a seq é a que já tenho,
   para aí (ler o arquivo inteiro a cada 0,1 s deixava o cursor lento). Devolve o tamanho lido ou -1. */
static int ler_tela(const char *nome, int so_se_nova)
{
    int fd = open(nome, O_RDONLY), n, total = 0;
    if (fd < 0) return -1;
    while (total < 20 && (n = read(fd, arq + total, 20 - total)) > 0) total += n;
    if (total == 20 && so_se_nova && memcmp(arq, "PST2", 4) == 0 && u32le(arq + 4) == minha_seq) {
        close(fd);
        return total;
    }
    while (total < BUF_MAX && (n = read(fd, arq + total, BUF_MAX - total > 65536 ? 65536 : BUF_MAX - total)) > 0)
        total += n;
    close(fd);
    return total;
}

/* Aplica os registros de um arquivo de tela. Devolve 0 se tudo certo. */
static int aplicar(int tam)
{
    int p = 20;
    while (p + 20 <= tam) {
        unsigned char *r = arq + p;
        unsigned int x = u16le(r + 4), y = u16le(r + 6), w = u16le(r + 8), h = u16le(r + 10);
        unsigned int ct = u32le(r + 12), crc = u32le(r + 16), lin;
        uLongf saida = (uLongf)w * h * 4;
        if (memcmp(r, "PSF2", 4) != 0 || p + 20 + (int)ct > tam) return -1;
        if (x + w > LARG || y + h > ALT || w == 0 || h == 0) return -1;
        if ((unsigned int)crc32(0L, r + 20, ct) != crc) return -1;
        if (uncompress(desc, &saida, r + 20, ct) != Z_OK || saida != (uLongf)w * h * 4) return -1;
        for (lin = 0; lin < h; lin++)
            memcpy(&quadro[(y + lin) * LARG + x], desc + lin * w * 4, w * 4);
        p += 20 + ct;
    }
    sujo = 1;
    return 0;
}

/* Busca tela nova. Devolve 1 se o notebook mandou sair. */
static int atualizar_tela(void)
{
    int tam = ler_tela("host:dif.bin", 1);
    unsigned int seq, base, cmd;
    if (tam < 20 || memcmp(arq, "PST2", 4) != 0) return 0;
    seq = u32le(arq + 4); base = u32le(arq + 8); cmd = u32le(arq + 12);
    if ((cmd & 0xFF) == 1) return 1;
    if ((cmd & 0x100) && !musica && (musica = carregar_som("host:musica.raw", &musica_n)) == NULL) musica_n = 0;
    musica_ligada = (cmd & 0x100) != 0;
    if (cmd & 0x200) pedido_pendente = 1;
    if (seq == minha_seq) return pedido_pendente ? (pedido_pendente = 0, 2) : 0;
    if (base == minha_seq && base != 0 && aplicar(tam) == 0) { minha_seq = seq; return pedido_pendente ? (pedido_pendente = 0, 2) : 0; }
    tam = ler_tela("host:completa.bin", 0);   /* perdi alguma mudança: tela inteira */
    if (tam >= 20 && memcmp(arq, "PST2", 4) == 0 && aplicar(tam) == 0)
        minha_seq = u32le(arq + 4);
    return pedido_pendente ? (pedido_pendente = 0, 2) : 0;
}

static void escrever_entrada(unsigned short botoes, int cx, int cy, int rx, int ry)
{
    unsigned char m[20 + 64 + 12];
    int fd;
    memcpy(m, "PSI2", 4);
    m[4] = botoes & 0xFF; m[5] = botoes >> 8;
    m[6] = cx & 0xFF; m[7] = cx >> 8;
    m[8] = cy & 0xFF; m[9] = cy >> 8;
    m[10] = (signed char)rx; m[11] = (signed char)ry;
    memcpy(m + 12, &minha_seq, 4);
    m[16] = n_teclas & 0xFF; m[17] = n_teclas >> 8;
    m[18] = (signed char)(roda > 127 ? 127 : (roda < -127 ? -127 : roda)); m[19] = 0;
    memcpy(m + 20, teclas, 64);
    memcpy(m + 84, &pedido_id, 4);
    m[88] = pedido_estado; m[89] = pedido_pct; m[90] = usb_carregado; m[91] = video_ativo;
    { int p = video_pos_ms; memcpy(m + 92, &p, 4); }   /* posição do vídeo em ms (áudio tocado) */
    roda = 0;
    fd = open("host:entrada.bin", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) { write(fd, m, sizeof(m)); close(fd); }
}

static void guardar_tecla(unsigned char c)
{
    teclas[n_teclas % 64] = c;
    n_teclas++;
}

/* Drivers de pendrive USB, só na primeira cópia (bdm precisa do iomanX; se o PS2Link não tiver, carrega). */
static int carregar_usb(void)
{
    int r = 0;
    if (usb_carregado) return usb_carregado == 1;
    if (SifExecModuleBuffer(BDM_irx, size_BDM_irx, 0, NULL, &r) < 0 || r == 1) {
        SifExecModuleBuffer(IOMANX_irx, size_IOMANX_irx, 0, NULL, NULL);
        if (SifExecModuleBuffer(BDM_irx, size_BDM_irx, 0, NULL, &r) < 0) { usb_carregado = 3; return 0; }
        usb_carregado = 2;   /* 2 = precisou do iomanX (informativo) */
    }
    SifExecModuleBuffer(BDMFS_irx, size_BDMFS_irx, 0, NULL, NULL);
    SifExecModuleBuffer(USBMASS_irx, size_USBMASS_irx, 0, NULL, NULL);
    if (!usb_carregado) usb_carregado = 1;
    DelayThread(1500000);    /* o pendrive leva um tempo para aparecer */
    return 1;
}

/* cópia host: → mass: em segundo plano (o fio do ps2sdk serializa as chamadas com _fio_io_sema) */
static volatile int copia_ativa = 0;
static char copia_origem[129], copia_destino[129];
static unsigned int copia_tam, copia_id;
static u8 pilha_copia[16 * 1024] __attribute__((aligned(16)));

static void thread_copia(void *arg)
{
    static unsigned char buf[64 * 1024] __attribute__((aligned(64)));
    char pasta[129], *barra;
    unsigned int feito = 0;
    int in, out, n, estado = 1;
    (void)arg;
    strcpy(pasta, copia_destino);
    if ((barra = strrchr(pasta, '/')) && barra > pasta + 6) { *barra = 0; mkdir(pasta, 0777); }
    if ((in = open(copia_origem, O_RDONLY)) < 0) estado = 4;
    else if ((out = open(copia_destino, O_WRONLY | O_CREAT | O_TRUNC, 0644)) < 0) { close(in); estado = 5; }
    else {
        while ((n = read(in, buf, sizeof(buf))) > 0) {
            if (parar_threads) { estado = 6; break; }   /* saindo: fecha os arquivos e para */
            if (write(out, buf, n) != n) { estado = 6; break; }
            feito += n;
            if (pedido_id == copia_id) pedido_pct = copia_tam ? (feito * 100ULL / copia_tam) : 0;
        }
        close(in);
        close(out);
        if (estado == 1) estado = (copia_tam && feito != copia_tam) ? 6 : 2;
    }
    if (pedido_id == copia_id) { pedido_estado = estado; if (estado == 2) pedido_pct = 100; }
    copia_ativa = 0;
    ExitDeleteThread();
}

static void copiar_pedido(void)
{
    char origem[129], destino[129];
    unsigned int id, tam, op;
    int fd, in, n, total = 0;

    {   /* lê o pedido inteiro */
        unsigned char p[4 + 8 + 256 + 4];
        fd = open("host:pedido.bin", O_RDONLY);
        if (fd < 0) return;
        total = 0;
        while (total < (int)sizeof(p) && (n = read(fd, p + total, sizeof(p) - total)) > 0) total += n;
        close(fd);
        if (total < (int)sizeof(p) || memcmp(p, "PSP1", 4) != 0) return;
        id = u32le(p + 4); tam = u32le(p + 8);
        memcpy(origem, p + 12, 128); origem[128] = 0;
        memcpy(destino, p + 140, 128); destino[128] = 0;
        op = u32le(p + 268);
    }
    if (id == pedido_feito) return;
    pedido_id = id; pedido_estado = 1; pedido_pct = 0;
    if (op == 2) {   /* tocar vídeo: origem = .m2v, destino = .pcm (host:video/...), sem pendrive */
        char *ponto;
        strcpy(video_m2v, origem); strcpy(video_pcm, destino); strcpy(video_fim, origem);
        if ((ponto = strrchr(video_fim, '.'))) strcpy(ponto, ".fim");
        pedido_estado = 8; pedido_feito = id;
        video_pedido = 1;
        return;
    }
    if (!carregar_usb()) { pedido_estado = 3; pedido_feito = id; return; }
    if (op == 1) {   /* executar do pendrive: confere que existe, avisa o notebook e sai para ele */
        if ((in = open(origem, O_RDONLY)) < 0) { pedido_estado = 4; pedido_feito = id; return; }
        close(in);
        if (destino[0] != '-' && !strchr(destino, '|')) {   /* argumento = arquivo (ROM): confere; "-bsd=..." (Neutrino) não */
            if ((in = open(destino, O_RDONLY)) < 0) { pedido_estado = 5; pedido_feito = id; return; }
            close(in);
        }
        strcpy(exec_elf, origem); strcpy(exec_arg, destino);
        pedido_estado = 7; pedido_pct = 100; pedido_feito = id;
        pedido_sair = 2;   /* o laço principal fecha tudo e roda exec_elf */
        return;
    }
    if (op == 3) {   /* apagar do pendrive (cinema: "Baixados" → apagar) */
        pedido_estado = remove(origem) == 0 ? 2 : 4;
        pedido_feito = id;
        return;
    }
    /* op 0, copiar: numa thread própria (um episódio leva minutos pela USB 1.1; a tela não pode parar) */
    if (copia_ativa) return;   /* o notebook manda um pedido por vez; este volta na próxima leitura */
    strcpy(copia_origem, origem); strcpy(copia_destino, destino);
    copia_tam = tam; copia_id = id;
    pedido_feito = id;
    copia_ativa = 1;
    {
        ee_thread_t t;
        int tid;
        memset(&t, 0, sizeof(t));
        t.func = thread_copia; t.stack = pilha_copia; t.stack_size = sizeof(pilha_copia);
        t.gp_reg = &_gp; t.initial_priority = 0x52;
        if ((tid = CreateThread(&t)) >= 0) StartThread(tid, NULL);
        else { copia_ativa = 0; pedido_estado = 6; }
    }
}

/* ---------------- thread de comunicação ----------------
   Toda a E/S com o notebook (host:) fica aqui; o laço principal só lê o controle e desenha a 60 quadros/s. */
static u8 pilha_rede[64 * 1024] __attribute__((aligned(16)));

/* Temperatura do sensor ligado ao Mechacon (comando S 0x03/0xEF, como o PS2Ident e o AthenaEnv).
   Devolve décimos de °C, ou -1 se este modelo não tem (Mechacon antes do 5.04). */
static int ler_temperatura(void)
{
    unsigned char in[1] = { 0xEF }, out[16];
    short t;
    memset(out, 0, sizeof(out));
    if (!sceCdApplySCmd(0x03, in, sizeof(in), out) || out[0]) return -1;
    t = (short)(out[1] << 8 | out[2]);   /* 1/128 °C com sinal (cdvdman_152_get_temperature do ps2sdk) */
    return t * 10 / 128;
}

static void escrever_temperatura(void)
{
    char txt[16];
    int d = ler_temperatura(), fd;
    if (d <= 0) return;
    snprintf(txt, sizeof(txt), "%d.%d\n", d / 10, d % 10);
    if ((fd = open("host:temperatura.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644)) >= 0) {
        write(fd, txt, strlen(txt));
        close(fd);
    }
}

static void thread_rede(void *arg)
{
    unsigned short ult_b = 0xFFFF, ult_t = 0xFFFF;
    int ult_x = -1, ult_y = -1, desde_escrita = 0, desde_tela = 0, desde_temp = 10000;
    (void)arg;
    for (;;) {
        unsigned short b = in_botoes;
        if (parar_threads) { rede_parada = 1; SleepThread(); }
        int x = in_cx, y = in_cy, rx = in_rx, ry = in_ry;
        if (b != ult_b || x != ult_x || y != ult_y || rx || ry || roda || n_teclas != ult_t || desde_escrita >= 2000) {
            escrever_entrada(b, x, y, rx, ry);
            ult_b = b; ult_x = x; ult_y = y; ult_t = n_teclas; desde_escrita = 0;
        }
        if (desde_tela >= 100) {
            int r = atualizar_tela();
            if (r == 1) pedido_sair = 1;
            if (r == 2) { copiar_pedido(); escrever_entrada(in_botoes, in_cx, in_cy, 0, 0); }
            desde_tela = 0;
        }
        if (desde_temp >= 10000) { escrever_temperatura(); desde_temp = 0; }
        DelayThread(20000);
        desde_escrita += 20; desde_tela += 20; desde_temp += 20;
    }
}

static void iniciar_rede(void)
{
    ee_thread_t t;
    int id;
    memset(&t, 0, sizeof(t));
    t.func = thread_rede; t.stack = pilha_rede; t.stack_size = sizeof(pilha_rede);
    t.gp_reg = &_gp; t.initial_priority = 0x50;   /* acima do laço de desenho (0x7E), abaixo do som (0x40) */
    if ((id = CreateThread(&t)) >= 0) { StartThread(id, NULL); id_rede = id; }
}

static void parar_tudo(void)
{
    int i;
    parar_threads = 1;
    for (i = 0; i < 300; i++) {   /* até 3 s: som e rede no SleepThread, cópia fechou os arquivos */
        if ((id_som < 0 || som_parado) && (id_rede < 0 || rede_parada) && !copia_ativa) break;
        DelayThread(10000);
    }
    if (id_som >= 0) { TerminateThread(id_som); DeleteThread(id_som); }
    if (id_rede >= 0) { TerminateThread(id_rede); DeleteThread(id_rede); }
}

/* ---------------- controle ---------------- */
static void abrir_controle(void)
{
    int t;
    padInit(0);
    padPortOpen(0, 0, padBuf);
    for (t = 0; t < 300; t++) {
        int st = padGetState(0, 0);
        if (st == PAD_STATE_STABLE || st == PAD_STATE_FINDCTP1) break;
        gsKit_vsync_wait();
    }
    padSetMainMode(0, 0, PAD_MMODE_DUALSHOCK, PAD_MMODE_LOCK);
}

static int eixo(int v)            /* 0..255 → -127..127 com zona morta */
{
    v -= 128;
    if (v > -28 && v < 28) return 0;
    return v > 127 ? 127 : v;
}

#include "video.inc.c"

/* ---------------- desenho ---------------- */
static void desenhar(float cx, float cy)
{
    u64 branco = GS_SETREG_RGBAQ(0xFF, 0xFF, 0xFF, 0x80, 0), preto = GS_SETREG_RGBAQ(0, 0, 0, 0x80, 0);

    gsKit_clear(gs, GS_SETREG_RGBAQ(0x10, 0x20, 0x50, 0x80, 0));
    if (minha_seq) {
        if (sujo) {
            sujo = 0;
            SyncDCache(quadro, (u8 *)quadro + LARG * ALT * 4);
            gsKit_texture_upload(gs, &tela);
        }
        gsKit_prim_sprite_texture(gs, &tela, 0, 0, 0, 0, LARG, ALT, LARG, ALT, 1, GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0));
    } else {   /* esperando a primeira tela: barra pulsando */
        static int f = 0;
        float l = 40 + (f++ % 120) * 3;
        gsKit_prim_sprite(gs, 320 - l, 216, 320 + l, 232, 1, GS_SETREG_RGBAQ(0x40, 0x80, 0xFF, 0x80, 0));
    }
    gsKit_prim_triangle(gs, cx - 1, cy - 2, cx - 1, cy + 22, cx + 16, cy + 16, 2, preto);
    gsKit_prim_triangle(gs, cx + 1, cy + 2, cx + 1, cy + 17, cx + 12, cy + 14, 3, branco);
    gsKit_queue_exec(gs);
    gsKit_sync_flip(gs);
}

static void voltar_ps2link(void)
{
    /* IOP limpo + memory card; o carregador de ELF do ps2sdk lê o PS2LINK.ELF do card */
    sceSifInitRpc(0);
    while (!SifIopReset("", 0)) {};
    while (!SifIopSync()) {};
    sceSifInitRpc(0);
    SifLoadFileInit();
    SifInitIopHeap();
    sbv_patch_enable_lmb();
    sbv_patch_disable_prefix_check();
    if (SifLoadModule("rom0:XSIO2MAN", 0, NULL) < 0)
        SifLoadModule("rom0:SIO2MAN", 0, NULL);
    if (SifLoadModule("rom0:XMCMAN", 0, NULL) >= 0)   /* Slim: XMCMAN; antigos: MCMAN */
        SifLoadModule("rom0:XMCSERV", 0, NULL);
    else {
        SifLoadModule("rom0:MCMAN", 0, NULL);
        SifLoadModule("rom0:MCSERV", 0, NULL);
    }
    {
        char *a1[] = {"mc1:/APPS/PS2LINK/PS2LINK.ELF"}, *a0[] = {"mc0:/APPS/PS2LINK/PS2LINK.ELF"};
        LoadELFFromFile(a1[0], 1, a1);
        LoadELFFromFile(a0[0], 1, a0);
    }
    LoadExecPS2("rom0:OSDSYS", 0, NULL);
}

/* Aberto pelo OPL: IOP limpo + a rede do PS2Link com o host: do navlink.irx (porta 0x4721). */
static void reiniciar_iop(void)
{
    sceSifInitRpc(0);
    while (!SifIopReset("", 0)) {};
    while (!SifIopSync()) {};
    sceSifInitRpc(0);
    SifLoadFileInit();
    SifInitIopHeap();
    sbv_patch_enable_lmb();
    sbv_patch_disable_prefix_check();
}

/* IP do PS2 configurável (17/10/2026): IPCONFIG.DAT ao lado do navegador.elf no pendrive ("IP MÁSCARA GATEWAY", o
   formato do PS2Link). Lido uma vez: IOP só com o driver do pendrive, depois reinicia de novo para a rede.
   O app instalador (celular) e a TV box gravam esse arquivo; sem ele fica 192.168.4.230. */
static char cfg_ip[16] = "192.168.4.230", cfg_mascara[16] = "255.255.255.0", cfg_gw[16] = "192.168.4.1";
static int cfg_lido = 0;

static void ler_ipconfig(int argc, char *argv[])
{
    char caminho[160], buf[96], *campo[3];
    int fd = -1, t, n = 0, i;
    if (cfg_lido) return;
    cfg_lido = 1;
    strcpy(caminho, "mass:/APPS/NAVEGADOR/IPCONFIG.DAT");
    if (argc > 0 && argv[0] && !strncmp(argv[0], "mass", 4) && strlen(argv[0]) < sizeof(caminho) - 16) {
        char *barra;
        strcpy(caminho, argv[0]);
        if ((barra = strrchr(caminho, '/')) || (barra = strrchr(caminho, ':'))) strcpy(barra + 1, "IPCONFIG.DAT");
    }
    reiniciar_iop();
    SifExecModuleBuffer(IOMANX_irx, size_IOMANX_irx, 0, NULL, NULL);
    SifExecModuleBuffer(BDM_irx, size_BDM_irx, 0, NULL, NULL);
    SifExecModuleBuffer(BDMFS_irx, size_BDMFS_irx, 0, NULL, NULL);
    SifExecModuleBuffer(USBD_irx, size_USBD_irx, 0, NULL, NULL);
    SifExecModuleBuffer(USBMASS_irx, size_USBMASS_irx, 0, NULL, NULL);
    for (t = 0; t < 30 && fd < 0; t++) {   /* o pendrive leva até ~3 s para aparecer */
        DelayThread(100000);
        fd = open(caminho, O_RDONLY);
    }
    if (fd < 0) return;
    memset(buf, 0, sizeof(buf));
    n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    for (i = 0; i < n; i++) if (buf[i] == ' ' || buf[i] == '\r' || buf[i] == '\n' || buf[i] == '\t') buf[i] = 0;
    for (i = 0, t = 0; i < n && t < 3; i++)   /* três campos separados por espaço/quebra de linha */
        if (buf[i] && (i == 0 || !buf[i - 1])) campo[t++] = buf + i;
    if (t >= 1 && strlen(campo[0]) >= 7 && strlen(campo[0]) <= 15) strcpy(cfg_ip, campo[0]);
    if (t >= 2 && strlen(campo[1]) >= 7 && strlen(campo[1]) <= 15) strcpy(cfg_mascara, campo[1]);
    if (t >= 3 && strlen(campo[2]) >= 7 && strlen(campo[2]) <= 15) strcpy(cfg_gw, campo[2]);
}

static void ligar_rede_propria(int argc, char *argv[])
{
    const char *ip, *mascara, *gw;
    char conf[64];
    int i, n;
    ler_ipconfig(argc, argv);
    ip = cfg_ip; mascara = cfg_mascara; gw = cfg_gw;
    for (i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "ip=", 3)) ip = argv[i] + 3;
        else if (!strncmp(argv[i], "mascara=", 8)) mascara = argv[i] + 8;
        else if (!strncmp(argv[i], "gw=", 3)) gw = argv[i] + 3;
    }
    /* ps2ip-nm recebe "IP\0MÁSCARA\0GATEWAY\0", como o PS2Link manda (IPCONFIG.DAT) */
    memset(conf, 0, sizeof(conf));
    n = 0;
    strncpy(conf + n, ip, 15); n += strlen(conf + n) + 1;
    strncpy(conf + n, mascara, 15); n += strlen(conf + n) + 1;
    strncpy(conf + n, gw, 15); n += strlen(conf + n) + 1;

    if (cfg_lido == 1) {   /* acabou de ler o pendrive: os clientes de RPC são do IOP de antes */
        fioExit();
        SifExitIopHeap();
        SifLoadFileExit();
        cfg_lido = 2;
    }
    reiniciar_iop();
    /* mesma ordem e mesmos módulos do PS2Link (o Neutrino roda em cima disso; udptty = printf pela rede, porta 18194) */
    SifExecModuleBuffer(POWEROFF_irx, size_POWEROFF_irx, 0, NULL, NULL);
    SifExecModuleBuffer(DEV9_irx, size_DEV9_irx, 0, NULL, NULL);
    SifExecModuleBuffer(NETMAN_irx, size_NETMAN_irx, 0, NULL, NULL);
    SifExecModuleBuffer(SMAP_irx, size_SMAP_irx, 0, NULL, NULL);
    SifExecModuleBuffer(PS2IP_irx, size_PS2IP_irx, n, conf, NULL);
    SifExecModuleBuffer(UDPTTY_irx, size_UDPTTY_irx, 0, NULL, NULL);
    SifExecModuleBuffer(IOPTRAP_irx, size_IOPTRAP_irx, 0, NULL, NULL);
    SifExecModuleBuffer(NAVLINK_irx, size_NAVLINK_irx, 0, NULL, NULL);
}

/* Modo rede própria: espera o notebook conectar no navlink (servidor_host.py tenta a cada 2 s). */
static void esperar_notebook(void)
{
    for (;;) {
        int fd = open("host:clique.raw", O_RDONLY), i;
        if (fd >= 0) { close(fd); return; }
        for (i = 0; i < 30; i++) desenhar(LARG / 2, ALT / 2);   /* barra pulsando, ~0,5 s */
    }
}

static int modo_rede;   /* aberto pelo OPL: host: é o navlink (TV box/notebook) */

/* Abre um ELF como o PS2Link faz no execee (17/10/2026): o IOP (já limpo, só rede + navlink) carrega o ELF pelo
   host: com SifLoadElf e ele roda como uma thread nova; este programa fica dormindo por baixo. O elf-loader do ps2sdk
   reinicia o IOP antes de ler ("loadelf: ... Cannot openfile") e um ExecPS2 direto travava o Neutrino. O Neutrino
   lê config/ e modules/ pelo host: e depois monta sozinho o ambiente do jogo. Volta se não der. */
/* Pilha e argumentos da thread nova no ALTO da memória: o Neutrino é compactado e se descompacta em 0x100000, por
   cima deste programa (no PS2 real ele morria logo depois do SifLoadElf). O PS2Link também mora no alto. */
#define ALTO_PILHA ((u8 *)0x01F00000)
#define ALTO_PILHA_TAM (64 * 1024)
#define ALTO_ARGS ((struct sargs_start *)0x01F10000)
#define ALTO_UID ((int *)0x01F10200)

static void executar_como_ps2link(const char *caminho, int n, char **args)
{
    struct sargs_start *ua = ALTO_ARGS;
    t_ExecData ed;
    ee_thread_t th;
    int k, t = 0, id;
    if (SifLoadElf(caminho, &ed) < 0 || !ed.epc) return;
    gsKit_deinit_global(gs);   /* tira o tratador de vsync do gsKit: o código dele vai ser sobrescrito */
    FlushCache(0);
    FlushCache(2);
    memset(ua, 0, sizeof(*ua));
    for (k = -1; k < n && k < MAX_ARGS - 1; k++) {   /* argv[0] = o próprio caminho, depois os argumentos */
        const char *a = k < 0 ? caminho : args[k];
        int l = strlen(a);
        if (t + l + 1 > MAX_ARGLEN) break;
        memcpy(ua->args.payload + t, a, l + 1);
        ua->args.argv[ua->args.argc++] = ua->args.payload + t;
        t += l + 1;
    }
    memset(&th, 0, sizeof(th));
    th.func = (void *)ed.epc; th.stack = ALTO_PILHA; th.stack_size = ALTO_PILHA_TAM;
    th.gp_reg = (void *)ed.gp; th.initial_priority = 64;
    if ((id = CreateThread(&th)) < 0) return;
    *ALTO_UID = id;
    ua->pid = (int)ALTO_UID;
    FlushCache(0);
    StartThread(id, ua);
    for (;;) SleepThread();
}

static int arg_n;
static char **arg_v;

int main(int argc, char *argv[])
{
    arg_n = argc; arg_v = argv;
    modo_rede = argc < 1 || !argv[0] || strncmp(argv[0], "host:", 5) != 0;
    {   /* "rede" nos argumentos força a rede própria mesmo vindo do PS2Link (teste sem copiar para o pendrive) */
        int i;
        for (i = 1; i < argc; i++) if (!strcmp(argv[i], "rede")) modo_rede = 1;
    }
    struct padButtonStatus pad;
    float cx = LARG / 2, cy = ALT / 2;
    unsigned short antes = 0;

    /* O laço principal espera o vsync em espera ativa: prioridade mínima para não atrapalhar o resto. */
    ChangeThreadPriority(GetThreadId(), 0x7E);

    /* Pelo PS2Link: sem reiniciar o IOP, o host: dele continua valendo. Pelo OPL: rede própria (navlink). */
    if (modo_rede) ligar_rede_propria(argc, argv);
    sceSifInitRpc(0);
    SifLoadFileInit();
    SifInitIopHeap();
    sbv_patch_enable_lmb();
    sbv_patch_disable_prefix_check();
    SifLoadModule("rom0:SIO2MAN", 0, NULL);
    SifLoadModule("rom0:PADMAN", 0, NULL);
    {   /* Bluetooth: usbd + ds34bt com 1 controle (como o OPL faz) */
        int pads = 1;
        SifExecModuleBuffer(USBD_irx, size_USBD_irx, 0, NULL, NULL);
        SifExecModuleBuffer(DS34BT_irx, size_DS34BT_irx, 4, (char *)&pads, NULL);
        ds34bt_init();
    }
    SifExecModuleBuffer(MOUSE_irx, size_MOUSE_irx, 0, NULL, NULL);
    SifExecModuleBuffer(KBD_irx, size_KBD_irx, 0, NULL, NULL);
    if (PS2MouseInit() >= 0) PS2MouseSetReadMode(PS2MOUSE_READMODE_DIFF);
    if (PS2KbdInit() >= 0) {
        PS2KbdSetReadmode(PS2KBD_READMODE_NORMAL);
        PS2KbdSetBlockingMode(PS2KBD_NONBLOCKING);
    }
    gs = gsKit_init_global();
    gs->PSM = GS_PSM_CT24;
    gs->ZBuffering = GS_SETTING_OFF;
    gs->DoubleBuffering = GS_SETTING_ON;
    dmaKit_init(D_CTRL_RELE_OFF, D_CTRL_MFD_OFF, D_CTRL_STS_UNSPEC, D_CTRL_STD_OFF, D_CTRL_RCYC_8, 1 << DMA_CHANNEL_GIF);
    dmaKit_chan_init(DMA_CHANNEL_GIF);
    gsKit_init_screen(gs);
    gsKit_mode_switch(gs, GS_ONESHOT);
    gs->PrimAlphaEnable = GS_SETTING_OFF;

    memset(&tela, 0, sizeof(tela));
    tela.Width = LARG; tela.Height = ALT; tela.PSM = GS_PSM_CT32; tela.Filter = GS_FILTER_NEAREST;
    tela.Mem = memalign(128, gsKit_texture_size_ee(LARG, ALT, GS_PSM_CT32));
    tela.Vram = gsKit_vram_alloc(gs, gsKit_texture_size(LARG, ALT, GS_PSM_CT32), GSKIT_ALLOC_USERBUFFER);
    quadro = (u32 *)tela.Mem;
    memset(quadro, 0, LARG * ALT * 4);
    arq = memalign(64, BUF_MAX);
    desc = memalign(64, LARG * ALT * 4);

    desenhar(cx, cy);
    if (modo_rede) esperar_notebook();
    iniciar_som();   /* lê host:clique.raw: depois da rede */
    abrir_controle();
    iniciar_rede();

    for (;;) {
        unsigned short botoes = 0;
        int rx = 0, ry = 0, lx = 0, ly = 0;

        if (video_pedido) {   /* cinema: toca até acabar/parar; ← → trazem outra sessão (resultado 11) */
            int r;
            do { r = tocar_video(); } while (r == 11);
            pedido_estado = r;   /* 9 acabou, 10 parado: o notebook encerra a conversão */
            escrever_entrada(0, (int)cx, (int)cy, 0, 0);
            continue;
        }

        if (padRead(0, 0, &pad) != 0) {
            botoes = 0xFFFF ^ pad.btns;
            if (pad.mode >> 4 == 0x7) {   /* DualShock (analógico) */
                rx = eixo(pad.rjoy_h); ry = eixo(pad.rjoy_v);
                lx = eixo(pad.ljoy_h); ly = eixo(pad.ljoy_v);
            }
        }
        if (ds34bt_get_status(0) & DS34BT_STATE_RUNNING) {   /* DualShock por Bluetooth */
            struct padButtonStatus bt;
            memset(&bt, 0, sizeof(bt));
            if (ds34bt_get_data(0, (u8 *)&bt.btns) != 0) {
                botoes |= 0xFFFF ^ bt.btns;
                if (!lx && !ly) { lx = eixo(bt.ljoy_h); ly = eixo(bt.ljoy_v); }
                if (!rx && !ry) { rx = eixo(bt.rjoy_h); ry = eixo(bt.rjoy_v); }
            }
        }
        {   /* mouse USB */
            PS2MouseData md;
            if (PS2MouseRead(&md) > 0) {
                cx += md.x; cy += md.y; roda -= md.wheel;
                if (md.buttons & PS2MOUSE_BTN1) botoes |= PAD_CROSS;
                if (md.buttons & PS2MOUSE_BTN2) botoes |= PAD_CIRCLE;
            }
        }
        {   /* teclado USB: ASCII; especiais vêm como ESC + código */
            char c;
            int novas = 0;
            while (PS2KbdRead(&c) > 0 && novas < 16) {
                if ((unsigned char)c == PS2KBD_ESCAPE_KEY) {
                    char e;
                    if (PS2KbdRead(&e) > 0) guardar_tecla(0x80 | (e & 0x7F));
                } else
                    guardar_tecla((unsigned char)c);
                novas++;
            }
        }
        if ((botoes & PAD_CROSS) && !(antes & PAD_CROSS) && clique) clique_pos = 0;   /* som do clique */
        antes = botoes;
        if ((botoes & (PAD_SELECT | PAD_START)) == (PAD_SELECT | PAD_START)) break;

        cx += lx * (lx < 0 ? -lx : lx) / 1600.0f;
        cy += ly * (ly < 0 ? -ly : ly) / 1600.0f;
        if (botoes & PAD_LEFT) cx -= 4;
        if (botoes & PAD_RIGHT) cx += 4;
        if (botoes & PAD_UP) cy -= 4;
        if (botoes & PAD_DOWN) cy += 4;
        if (cx < 0) cx = 0;
        if (cx > LARG - 1) cx = LARG - 1;
        if (cy < 0) cy = 0;
        if (cy > ALT - 1) cy = ALT - 1;

        in_botoes = botoes; in_cx = (int)cx; in_cy = (int)cy; in_rx = rx; in_ry = ry;   /* a thread de rede envia */
        if (pedido_sair) break;
        desenhar(cx, cy);
    }

    musica_ligada = 0;
    if (pedido_sair == 2) {   /* deixa o notebook ler o estado 7 antes de sumir */
        escrever_entrada(0, 0, 0, 0, 0);
        DelayThread(300000);
    }
    parar_tudo();
    audsrv_quit();
    padPortClose(0, 0);
    padEnd();
    if (pedido_sair == 2) {   /* RetroArch (ou outro ELF) do pendrive, com a ROM como argumento */
        /* o loader do ps2sdk já põe o caminho do ELF em argv[0]: aqui vai só a ROM (com {ELF, ROM} o emulador
           recebia o próprio .elf como argv[1]: RetroArch tela preta e SNESticle no menu, PS2 real 17/10/2026) */
        /* vários argumentos separados por '|' (Neutrino: "-bsd=udpfs|-dvd=udpfs:DVD/jogo.iso", jogo em nuvem) */
        char *args[8];
        int n = 0;
        char *p = exec_arg;
        while (n < 8) {
            char *barra = strchr(p, '|');
            args[n++] = p;
            if (!barra) break;
            *barra = 0;
            p = barra + 1;
        }
        if (modo_rede && !strncmp(exec_elf, "host:", 5)) {
            /* Neutrino pelo host: (17/10/2026): como o PS2Link faz no execee, IOP limpo só com a rede e o navlink
               antes de abrir. Com USB/Bluetooth/som/mouse ainda carregados o Neutrino voltava ao menu do console. */
            int t;
            fioExit();   /* os clientes de RPC do IOP antigo: religam depois do reinício */
            SifExitIopHeap();
            SifLoadFileExit();
            ligar_rede_propria(arg_n, arg_v);
            for (t = 0; t < 150; t++) {   /* até 15 s para a TV box reconectar no navlink */
                int fd = open("host:clique.raw", O_RDONLY);
                if (fd >= 0) { close(fd); break; }
                DelayThread(100000);
            }
            executar_como_ps2link(exec_elf, n, args);   /* só volta se não deu */
        }
        LoadELFFromFile(exec_elf, n, args);
    }
    voltar_ps2link();
    return 0;
}
