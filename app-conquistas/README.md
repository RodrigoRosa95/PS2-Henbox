# PS2 Conquistas (app Android do PS2 Henbox)

Painel das conquistas RetroAchievements do PS2 no celular, com **notificação a cada desbloqueio** (medalha, nome,
pontos e um plim de troféu). Faz parte do [PS2 Henbox](../README.md); os dados vêm da TV box (`videos.py`, porta 8780)
e do app [xeRAbora](https://github.com/hacan359/xerabora) que roda nela.

- **Acha a TV box sozinho:** pergunta `http://<vizinho>:8780/henbox` a todos os endereços da rede Wi-Fi do celular
  (a box responde `{"app": "ps2-henbox"}`); se o IP da box mudar, procura de novo ao abrir. Dá para digitar à mão no ⚙.
- **Abas:** *Ao vivo* (página do xeRAbora na box, porta 18280 — precisa do "OPEN TO THE NETWORK" ligado nele) e
  *Henbox* (página 🏆 do navegador). Em aparelho com WebView antigo (Chrome < 80) abre na aba Henbox.
- **Notificações:** serviço em primeiro plano consulta `/conquistas/api/desbloqueios?desde=` a cada 5 s; volta
  sozinho quando o celular liga. Fora de casa a box não responde e ele só espera.
- Android 4.4 ou mais novo (testado num Motorola Xoom com 4.4.4).

Montar: `./montar.sh` (Java puro, sem Gradle: javac + dx + aapt + apksigner do android-sdk, plataforma 23).
O APK pronto está em [`downloads/PS2Conquistas.apk`](../downloads/PS2Conquistas.apk).
