/*
 * navlink.irx (pedido do usuário 17/10/2026: navegador com rede direto no PS2, sem o PS2Link).
 * É só o servidor de arquivos host: do PS2Link (net_fsys.c/net_fio.c de github.com/ps2dev/ps2link, licença PS2Link),
 * na porta TCP 0x4721 em vez de 0x4711. O PS2 escuta; o notebook (navegador/servidor_host.py) conecta e serve a pasta
 * navegador/ps2/. Sem o tratador de comandos (execee/reset) nem o printf pela rede do PS2Link.
 * Precisa de ps2dev9 + netman + smap + ps2ip-nm carregados antes.
 */
#include <stdio.h>
#include <loadcore.h>
#include <intrman.h>
#include <types.h>

#include "net_fsys.h"

#define MODNAME "navlink"
IRX_ID(MODNAME, 1, 0);

int _start(int argc, char **argv)
{
    (void)argc; (void)argv;
    FlushDcache();
    CpuEnableIntr();
    fsysMount();
    printf("navlink: host: na porta 0x4721\n");
    return MODULE_RESIDENT_END;
}
