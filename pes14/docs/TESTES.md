# Testes

## Lógica da TV box com um PS2 simulado

```bash
cd pes14/notebook && python3 preparar_base.py && python3 atualizar_tudo.py --sem-raspar   # gera e publica
python3 ../tests/test_pes14.py
```

`test_pes14.py` troca o PS2 por pastas (cartão = uma pasta, `host:` = outra) e roda o `pes14.py` de verdade nestes
cenários: (1) atualização normal, com o backup idêntico ao original, ícones intocados e a barra de progresso
crescente de 2% a 100%; (2) repetir sem mudança; (3) desfazer; (4) gravação corrompida → o save anterior volta;
(5) download corrompido → nada é gravado; (6) sem save no cartão; (7) navegador fechando no meio.

## Abrir o save no PCSX2 sem tocar nos seus cartões

```bash
python3 -m venv ven && ven/bin/pip install mymcplus
ven/bin/mymcplus -i TestePES.ps2 format
ven/bin/mymcplus -i TestePES.ps2 mkdir BESLES-556762014OPT
ven/bin/mymcplus -i TestePES.ps2 add -d BESLES-556762014OPT novo/BESLES-556762014OPT novo/icon.sys novo/icon_view
```

Com o PCSX2 (Flatpak), uma pasta de dados própria evita mexer na sua configuração: coloque `bios/`, `memcards/TestePES.ps2` e
`inis/PCSX2.ini` (com `Slot1_Filename = TestePES.ps2`) numa pasta `xdg/PCSX2/` e rode
`flatpak run --env=XDG_CONFIG_HOME=$PWD/xdg --filesystem=$PWD net.pcsx2.PCSX2 -batch -- seu-pes2014.iso`.
(`-cfg` não funcionou nesse build.) Em 16/11/2026 o jogo abriu com o save e mostrou todas as ligas.
