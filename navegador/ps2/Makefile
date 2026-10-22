# Navegador do PS2 (cliente via host: do PS2Link, ou rede própria com o navlink.irx quando aberto pelo OPL). make → navegador.elf
# (versão com rede própria: Makefile.socket)
EE_BIN = navegador.elf
EE_OBJS = navegador.o USBD_irx.o DS34BT_irx.o MOUSE_irx.o KBD_irx.o LIBSD_irx.o AUDSRV_irx.o IOMANX_irx.o BDM_irx.o BDMFS_irx.o USBMASS_irx.o \
          DEV9_irx.o NETMAN_irx.o SMAP_irx.o PS2IP_irx.o NAVLINK_irx.o \
          POWEROFF_irx.o UDPTTY_irx.o IOPTRAP_irx.o
EE_INCS += -I$(GSKIT)/include -I$(PS2SDK)/ports/include
EE_LDFLAGS += -L$(GSKIT)/lib -L$(PS2SDK)/ports/lib -Lopl-ds34bt
# Ligado em 16 MB (22/10/2026), como o PS2Link mora no alto: o Neutrino do "Jogar pela rede" se descompacta em
# 0x100000 e, com o navegador ali, algum tratador dele ainda registrado no kernel era atropelado (EE congelava, qualquer jogo)
EE_LINKFILE = linkfile-alto
EE_LIBS = -lds34bt -lmouse -lkbd -laudsrv -lmpeg -lpacket -ldma -lelf-loader -lgskit -ldmakit -lz -lpad -lpatches

all: $(EE_BIN)
	$(EE_STRIP) $(EE_BIN)

clean:
	rm -f $(EE_BIN) $(EE_OBJS) USBD_irx.c DS34BT_irx.c MOUSE_irx.c KBD_irx.c LIBSD_irx.c AUDSRV_irx.c IOMANX_irx.c BDM_irx.c BDMFS_irx.c USBMASS_irx.c DEV9_irx.c NETMAN_irx.c SMAP_irx.c PS2IP_irx.c NAVLINK_irx.c POWEROFF_irx.c UDPTTY_irx.c IOPTRAP_irx.c

USBD_irx.c: $(PS2SDK)/iop/irx/usbd.irx
	bin2c $< $@ USBD_irx
DS34BT_irx.c: opl-ds34bt/ds34bt.irx
	bin2c $< $@ DS34BT_irx

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
MOUSE_irx.c: $(PS2SDK)/iop/irx/ps2mouse.irx
	bin2c $< $@ MOUSE_irx
KBD_irx.c: $(PS2SDK)/iop/irx/ps2kbd.irx
	bin2c $< $@ KBD_irx
LIBSD_irx.c: $(PS2SDK)/iop/irx/libsd.irx
	bin2c $< $@ LIBSD_irx
AUDSRV_irx.c: $(PS2SDK)/iop/irx/audsrv.irx
	bin2c $< $@ AUDSRV_irx
IOMANX_irx.c: $(PS2SDK)/iop/irx/iomanX.irx
	bin2c $< $@ IOMANX_irx
BDM_irx.c: $(PS2SDK)/iop/irx/bdm.irx
	bin2c $< $@ BDM_irx
BDMFS_irx.c: $(PS2SDK)/iop/irx/bdmfs_fatfs.irx
	bin2c $< $@ BDMFS_irx
USBMASS_irx.c: $(PS2SDK)/iop/irx/usbmass_bd.irx
	bin2c $< $@ USBMASS_irx

DEV9_irx.c: $(PS2SDK)/iop/irx/ps2dev9.irx
	bin2c $< $@ DEV9_irx
NETMAN_irx.c: $(PS2SDK)/iop/irx/netman.irx
	bin2c $< $@ NETMAN_irx
SMAP_irx.c: $(PS2SDK)/iop/irx/smap.irx
	bin2c $< $@ SMAP_irx
PS2IP_irx.c: $(PS2SDK)/iop/irx/ps2ip-nm.irx
	bin2c $< $@ PS2IP_irx
NAVLINK_irx.c: ../navlink/navlink.irx
	bin2c $< $@ NAVLINK_irx
POWEROFF_irx.c: $(PS2SDK)/iop/irx/poweroff.irx
	bin2c $< $@ POWEROFF_irx
UDPTTY_irx.c: $(PS2SDK)/iop/irx/udptty.irx
	bin2c $< $@ UDPTTY_irx
IOPTRAP_irx.c: $(PS2SDK)/iop/irx/ioptrap.irx
	bin2c $< $@ IOPTRAP_irx

navegador.o: video.inc.c
