# O Option File do PES 2014 (PS2, PAL)

Engenharia reversa feita em 16/11/2026 sobre o save `BESLES-556762014OPT` (1.086.464 bytes) do PES 2014 PAL
(`SLES-556.76`). O formato é o **mesmo do PES 6** (o [PESEditor](https://github.com/PeterC10/PESEditor) documenta a cifra);
o que muda é a tabela de blocos e o tamanho das tabelas. Tudo abaixo foi **verificado** em um save real: decifrar,
cifrar de novo e recalcular os checksums devolve o arquivo original byte a byte (`notebook/preparar_base.py` repete
essa prova no seu save antes de qualquer edição).

## Blocos

O arquivo é uma sequência de **11 blocos**. Cada um tem um cabeçalho de 12 bytes (`u32` little-endian):

```
[tamanho] [checksum] [0x200] [dados ... tamanho bytes]
```

- **Cifra** (blocos 1 a 10; o bloco 0 não é cifrado), por palavra de 32 bits, com `K = 0x7ab3684c`:
  `cifrado = CHAVE[k] + ((claro ^ K) - K)` (módulo 2³²), onde `k` vai de 0 a 445 e **recomeça em cada bloco**.
  Decifrar: `claro = ((cifrado - CHAVE[k]) + K) ^ K`.
- **Checksum**: soma (módulo 2³²) de todas as palavras de 32 bits dos dados **já cifrados**, gravada 8 bytes antes do
  início dos dados.
- A `CHAVE` (446 palavras) **não está neste repositório**: é a tabela do `OptionFile.java` do PESEditor
  (`ref/PESEditor/src/editor/OptionFile.java`). É a mesma do PES 6.

| # | Início dos dados | Tamanho | Conteúdo |
|---|---|---|---|
| 0 | `0x00000c` | 4852 | cabeçalho do jogo (não cifrado) |
| 1 | `0x001418` | 2296 | |
| 2 | `0x001db8` | 4224 | estádios (nomes) |
| 3 | `0x002e44` | 22816 | 184 jogadores **editados** (184 × 124) |
| 4 | `0x008770` | 605120 | **4880 jogadores** (4880 × 124) |
| 5 | `0x09c678` | 90227 | camisas e **elencos dos times** (tamanho que não é múltiplo de 4: o último trecho é preenchimento) |
| 6 | `0x0b26f8` | 11440 | **130 times** (130 × 88): nomes |
| 7 | `0x0b53b4` | 163432 | |
| 8 | `0x0dd228` | 155624 | |
| 9 | `0x10321c` | 2596 | |
| 10 | `0x1040fc` | 20456 | |

## O que o projeto lê e escreve (offsets no arquivo **decifrado**)

| O quê | Onde | Formato |
|---|---|---|
| Jogador *i* | `0x8770 + 124·i` | 124 bytes. Nome nos 32 primeiros bytes (UTF-16LE, termina em `00 00`) |
| Altura | registro `+88`, 6 bits baixos | `valor + 148` cm |
| Idade | registro `+112`, bits 9–13 | `valor + 15` (idade na época do patch-base) |
| Nacionalidade | registro `+112`, 7 bits baixos | índice numa tabela que **difere da do PES 6** (não usada) |
| Nome do time *k* | `0xb26f8 + 88·k` | 48 bytes (latin-1) |
| Elenco do time *k* | `0x9ec10 + 64·k` | 32 vagas × `u16` (id do jogador; `0` = vaga livre). Mesma ordem dos nomes |
| Camisas do time *k* | `0x9ce40 + 32·k` | 32 bytes (`255` = sem número). **Alinhamento ainda não confirmado** |

No save de teste havia 130 times: 126 clubes reais e 4 fictícios (`ALL STARS TFC`, …).

## Como as transferências são aplicadas (`notebook/gerar.py`)

1. Decifra o Option File base.
2. **Passagem 1:** tira cada jogador a mover do(s) clube(s) onde está e preenche o buraco com o último do elenco (o prefixo
   do elenco continua sem buracos).
3. **Passagem 2:** põe cada jogador na primeira vaga livre do clube novo (camisa `255`). Sem vaga, volta ao clube antigo.
4. Cifra de novo e recalcula os 11 checksums.

## Em aberto

- Alinhamento da tabela de camisas com as vagas do elenco.
- Tabela de nacionalidades do PES 2014.
- Seleções nacionais (23 vagas por time) não foram localizadas.
- Criar jogadores novos (nome, aparência, atributos) reaproveitando vagas de aposentados.
