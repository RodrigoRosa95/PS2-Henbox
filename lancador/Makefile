# abrir.elf: abre um ELF do memory card a partir do PS2Link (ver abrir.c). make → abrir.elf
EE_BIN = abrir.elf
EE_OBJS = abrir.o
EE_LIBS = -lelf-loader -lpatches

all: $(EE_BIN)
	$(EE_STRIP) $(EE_BIN)

clean:
	rm -f $(EE_BIN) $(EE_OBJS)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
