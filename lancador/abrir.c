/*
 * abrir.elf (pedido do usuário 17/10/2026): o PS2Link não tem driver de memory card ("Unknown device 'mc'"),
 * então "ps2client execee mc0:/BOOT/BOOT.ELF" não funciona. Este .elf vai pelo host: e abre o ELF do argumento:
 *   ps2client -h 192.168.4.230 execee host:abrir.elf mc0:/BOOT/BOOT.ELF
 * Reinicia o IOP, carrega SIO2MAN/MCMAN/MCSERV da ROM e chama o elf-loader. Sem argumento: mc0:/BOOT/BOOT.ELF.
 * Vários argumentos = tenta cada caminho em ordem (o elf-loader volta quando não acha o arquivo).
 */
#include <string.h>
#include <kernel.h>
#include <iopcontrol.h>
#include <iopheap.h>
#include <sifrpc.h>
#include <loadfile.h>
#include <sbv_patches.h>
#include <elf-loader.h>

int main(int argc, char *argv[])
{
    char *padrao = "mc0:/BOOT/BOOT.ELF";
    int i;

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
    if (argc < 2) { char *args[] = {padrao}; LoadELFFromFile(padrao, 1, args); }
    for (i = 1; i < argc; i++) { char *args[] = {argv[i]}; LoadELFFromFile(argv[i], 1, args); }
    LoadExecPS2("rom0:OSDSYS", 0, NULL);   /* não achou: menu do console */
    return 0;
}
