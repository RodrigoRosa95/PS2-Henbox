# navlink.irx: servidor host: do PS2Link na porta 0x4721 (ver navlink.c). make → navlink.irx
IOP_BIN  = navlink.irx
IOP_OBJS = net_fsys.o net_fio.o navlink.o imports.o

IOP_INCS += -Iinclude
IOP_CFLAGS += -Werror

all: $(IOP_BIN)

clean:
	-rm -f $(IOP_OBJS) $(IOP_BIN)

include $(PS2SDK)/Defs.make
include $(PS2SDK)/samples/Makefile.iopglobal
