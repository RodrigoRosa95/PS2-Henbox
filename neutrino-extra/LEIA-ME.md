# DualShock 3/4 por Bluetooth nos jogos do Neutrino

O "☁ Jogar pela rede" abre o jogo pelo [Neutrino](https://github.com/rickgaiser/neutrino) com `-cfg=pademu`, que carrega
no ambiente do jogo o **PadEmu do Open PS2 Loader** (`bt_pademu.irx`): ele intercepta o SIO2MAN e entrega os botões do
DualShock 3/4 pareado com o adaptador Bluetooth USB como se fosse um DualShock 2 na porta 1.

| Arquivo | Vai em | O que é |
| --- | --- | --- |
| `pademu/` | — | código do PadEmu (OPL `modules/pademu`, AFL-3.0), sem o `smsutils` que o Neutrino não tem |
| `bt_pademu.irx` | `neutrino/modules/` | compilado: `make -C pademu USE_BT=1` (ps2sdk) |
| `pademu.toml` | `neutrino/config/` | carrega `usbd_mini.irx` (com menos memória) e o `bt_pademu.irx` no jogo |

Para desligar: apague `neutrino/config/pademu.toml` na TV box (o navegador só passa `-cfg=pademu` se o arquivo existir).
Ainda não testado no PS2 real.
