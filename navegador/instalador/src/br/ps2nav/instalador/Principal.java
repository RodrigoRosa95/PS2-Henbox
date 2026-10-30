package br.ps2nav.instalador;

import android.app.Activity;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.Socket;
import java.security.KeyPair;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * Instalador do PS2 Navegador (celular → TV box com root, pedido do usuário 17/10/2026): acha a TV box na rede
 * (ADB na porta 5555), conecta (a TV pede "Permitir depuração" na 1ª vez), instala Termux, Termux:Boot, o app
 * PS2 Navegador e os servidores, mostra o estado da box e troca o IP do PS2.
 */
public class Principal extends Activity {
    final Handler ui = new Handler(Looper.getMainLooper());
    final ExecutorService fila = Executors.newSingleThreadExecutor();
    LinearLayout achadas, pendrives;
    EditText campoBox, campoIp, campoMascara, campoGw, campoServidor, campoChave;
    TextView log, estado;
    Canal adb;
    Caixa caixa;
    String boxConectada = "";
    ScrollView rolagem;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        rolagem = new ScrollView(this);
        LinearLayout raiz = new LinearLayout(this);
        raiz.setOrientation(LinearLayout.VERTICAL);
        int m = dp(16);
        raiz.setPadding(m, m, m, m);
        rolagem.addView(raiz);
        setContentView(rolagem);

        titulo(raiz, "PS2 Henbox", 22);
        botao(raiz, "🎮 Central: capas, ISOs do celular, online, arquivos e controle", new Runnable() { public void run() { abrirCentral(); } });
        texto(raiz, "1. Conecte o celular no mesmo Wi-Fi da TV box (com ADB pela rede ligado). 2. Procure ou digite o IP. "
                + "3. Conecte e aceite \"Permitir depuração\" na TV.");
        botao(raiz, "Instalar NESTA TV box (este aparelho, com root)", new Runnable() { public void run() { conectarAqui(); } });
        texto(raiz, "Ou, do celular:");
        botao(raiz, "Procurar TV boxes na rede", new Runnable() { public void run() { procurar(); } });
        achadas = new LinearLayout(this);
        achadas.setOrientation(LinearLayout.VERTICAL);
        raiz.addView(achadas);
        campoBox = campo(raiz, "IP da TV box (ex.: 192.168.4.79)", "");
        botao(raiz, "Conectar", new Runnable() { public void run() { conectar(); } });

        titulo(raiz, "TV box", 18);
        botao(raiz, "Instalar / atualizar tudo", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { caixa.instalar(); mostrarChecklist(); } }); } });
        botao(raiz, "Ver estado", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { mostrarEstado(); } }); } });
        botao(raiz, "Reiniciar serviços", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { caixa.uidTermux = caixa.su("stat -c %u " + Caixa.T); caixa.iniciar();
                escrever("Serviços reiniciando (uns 20 s)…"); caixa.esperar(20000); mostrarEstado(); } }); } });
        botao(raiz, "🩺 Estado completo (o que falta)", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { mostrarChecklist(); } }); } });
        estado = texto(raiz, "Estado: conecte numa TV box.");
        estado.setTypeface(Typeface.MONOSPACE);

        titulo(raiz, "Servidor em nuvem (opcional)", 18);
        texto(raiz, "O PC com a sua coleção (servidor/instalar.sh mostra o endereço e a chave). Sem ele, a TV box "
                + "mostra só os jogos e vídeos dela.");
        campoServidor = campo(raiz, "Endereço(s), separados por vírgula (ex.: http://192.168.0.10:8781, https://meu.dominio)", "");
        campoChave = campo(raiz, "Chave", "");
        campoServidor.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        campoChave.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);   // não aparece na tela
        botao(raiz, "Salvar servidor na TV box", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception {
                caixa.configurarServidor(lido(campoServidor), lido(campoChave));
                escrever("Servidor salvo. Reiniciando os serviços…");
                caixa.iniciar(); caixa.esperar(20000); mostrarEstado(); } }); } });

        titulo(raiz, "Pendrive do PS2", 18);
        texto(raiz, "Espete o pendrive na USB da TV box (não precisa de PC): a box copia o PS2 Henbox com o IP certo. "
                + "Depois é só pôr o pendrive na USB da frente do PS2 e abrir OPL → Apps → PS2 Henbox.");
        botao(raiz, "Preparar pendrive (na USB da TV box)", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { listarPendrives(); } }); } });
        pendrives = new LinearLayout(this);
        pendrives.setOrientation(LinearLayout.VERTICAL);
        raiz.addView(pendrives);

        titulo(raiz, "🎵 Música da loja", 18);
        texto(raiz, "Escolha uma música (MP3 e afins) no celular e ela vai para a pasta MUSICAS do pendrive da "
                + "TV box; a box mesma converte para o som do PS2 (até 90 s) e a loja começa a tocar.");
        botao(raiz, "🎵 Escolher uma música e enviar ao pendrive da TV box", new Runnable() { public void run() { escolherMusica(); } });

        titulo(raiz, "🏆 Conquistas (RetroAchievements)", 18);
        texto(raiz, "O xeRAbora (app oficial do autor, baixado do GitHub dele) acompanha as conquistas no PS2 real; "
                + "a TV box prepara as listas sozinha. Você só entra com o seu usuário do RetroAchievements na TV.");
        botao(raiz, "Instalar conquistas na TV box", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { caixa.instalarXerabora(); } }); } });
        botao(raiz, "Ver conquistas e avisos neste aparelho", new Runnable() { public void run() { abrirConquistas(); } });

        titulo(raiz, "PS2", 18);
        texto(raiz, "Com o PS2 ligado direto no cabo da TV box, nada aqui precisa mudar: a box leva o PS2 para a "
                + "internet pelo Wi-Fi dela. O IP abaixo só importa com o PS2 no roteador; a box grava o IPCONFIG.DAT "
                + "no pendrive sozinha quando o navegador abre.");
        campoIp = campo(raiz, "IP do PS2", "192.168.4.230");
        campoMascara = campo(raiz, "Máscara", "255.255.255.0");
        campoGw = campo(raiz, "Gateway", "192.168.4.1");
        botao(raiz, "Salvar IP na TV box", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception {
                caixa.trocarIp(lido(campoIp), lido(campoMascara), lido(campoGw));
                escrever("IP salvo. A box grava no pendrive na próxima vez que o navegador abrir (ou prepare o pendrive "
                        + "de novo na USB da box). Reiniciando os serviços…");
                caixa.iniciar(); } }); } });
        texto(raiz, "Com o navegador aberto no PS2, gravar pela rede:");
        botao(raiz, "Gravar IP no pendrive do PS2", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception {
                escrever("PS2: " + caixa.gravarNoPendrive("IPCONFIG.DAT", "IPCONFIG.DAT")); } }); } });
        botao(raiz, "Gravar navegador.elf no pendrive do PS2", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception {
                escrever("PS2: " + caixa.gravarNoPendrive("navegador.elf", "navegador.elf"));
                escrever("PS2: " + caixa.gravarNoPendrive("opl/title.cfg", "title.cfg")); } }); } });

        titulo(raiz, "Registro", 18);
        log = texto(raiz, "");
        log.setTypeface(Typeface.MONOSPACE);
        log.setTextSize(12);
        // registro da última execução (o app pode ter sido fechado no meio, ou a tela recriada)
        try {
            java.util.List<String> linhas = new java.util.ArrayList<String>();
            java.io.BufferedReader r = new java.io.BufferedReader(new java.io.FileReader(new java.io.File(getFilesDir(), "registro.txt")));
            for (String l; (l = r.readLine()) != null; ) linhas.add(l);
            r.close();
            StringBuilder sb = new StringBuilder();
            for (String l : linhas.subList(Math.max(0, linhas.size() - 60), linhas.size())) sb.append(l).append('\n');
            log.setText(sb);
        } catch (Exception e) { }
        if (b == null) {   // a tela recriada (girar, teclado, voltar do Termux) não repete o comando
            porIntent(getIntent().getExtras());
            getIntent().removeExtra("acao");
        }
    }

    /** Comandos sem tocar na tela (ADB, TV sem toque — 18/10/2026):
     *  am start -n br.ps2nav.instalador/.Principal --es servidor "URL[, URL]" --es chave CHAVE --es acao instalar-aqui
     *  acao: instalar-aqui (instala nesta box), servidor-aqui (só salva o servidor nesta box), conectar-aqui;
     *  rolar: servidor | fim (mostra a parte do servidor ou o registro). */
    @Override
    protected void onNewIntent(android.content.Intent i) {   // singleTask: am start com o app aberto cai aqui
        super.onNewIntent(i);
        setIntent(i);
        porIntent(i.getExtras());
    }

    void porIntent(Bundle x) {
        android.net.Uri u = getIntent() != null ? getIntent().getData() : null;
        if (u != null && "henbox".equals(u.getScheme()) && "parear".equals(u.getHost())) parear(u);
        if (x == null) return;
        if (x.getString("servidor") != null) campoServidor.setText(x.getString("servidor"));
        if (x.getString("chave") != null) campoChave.setText(x.getString("chave"));
        final String rolar = x.getString("rolar", "");
        if (rolar.length() > 0) ui.postDelayed(new Runnable() { public void run() {
            if (rolar.equals("fim")) rolagem.fullScroll(View.FOCUS_DOWN);
            else rolagem.smoothScrollTo(0, Math.max(0, campoServidor.getTop() - dp(120)));
        } }, 800);
        String acao = x.getString("acao", "");
        if (!acao.endsWith("-aqui")) return;
        conectarAqui();
        if (acao.equals("conectar-aqui")) return;
        final boolean so_servidor = acao.equals("servidor-aqui");
        fila.submit(new Runnable() {
            public void run() {
                if (caixa == null) return;
                try {
                    if (!so_servidor) caixa.instalar();   // instala antes: numa box nova o configurar.py ainda não existe
                    if (so_servidor || lido(campoServidor).length() > 0) {
                        caixa.configurarServidor(lido(campoServidor), lido(campoChave));
                        escrever("Servidor salvo. Reiniciando os serviços…");
                        caixa.iniciar();
                        caixa.esperar(20000);
                    }
                    mostrarEstado();
                } catch (Exception e) {
                    escrever("Erro: " + e.getMessage());
                }
            }
        });
    }

    interface Tarefa { void rodar() throws Exception; }

    /** Uma coisa por vez, fora da tela; erros vão para o registro. */
    void tarefa(final Tarefa t) {
        if (caixa == null) { escrever("Conecte numa TV box primeiro."); return; }
        fila.submit(new Runnable() {
            public void run() {
                try {
                    t.rodar();
                } catch (Exception e) {
                    escrever("ERRO: " + e.getMessage());
                }
            }
        });
    }

    /** Mostrado quando a TV box não aparece na rede ou recusa a conexão (ideia do CetusPlay: guia para ligar o ADB). */
    static final String AJUDA_ADB = "Como ligar o ADB pela rede na TV box:\n"
            + " 1. Configurações → Sobre / Informações → clique 7 vezes em \"Número da versão\" (libera o modo desenvolvedor).\n"
            + " 2. Configurações → Opções do desenvolvedor → ligue \"Depuração USB\" e \"Depuração ADB pela rede\" (porta 5555).\n"
            + "    Em algumas boxes fica em Configurações → Sistema → ADB, ou no app \"Configurações\" da própria marca.\n"
            + " 3. Celular e TV box na mesma rede. Procure de novo ou digite o IP (Configurações → Rede da TV box).\n"
            + " 4. Quando conectar, aceite \"Permitir depuração\" na TV e marque \"Sempre permitir\".";

    /** O app rodando na própria TV box (instalado por pendrive/loja de apps): comandos como root, sem ADB. */
    void conectarAqui() {
        fila.submit(new Runnable() {
            public void run() {
                try {
                    if (adb != null) adb.fechar();
                    adb = new Local(getCacheDir());
                    caixa = new Caixa(adb, getAssets(), new Adb.Aviso() { public void aviso(String s) { escrever(s); } });
                    if (!caixa.temRoot()) {
                        escrever("Este aparelho não deu root ao app: aceite o pedido de root (SuperSU/Magisk) e toque de novo.");
                        caixa = null;
                        return;
                    }
                    boxConectada = "esta TV box";
                    escrever("Nesta TV box: " + caixa.sh("getprop ro.product.model") + " (Android "
                            + caixa.sh("getprop ro.build.version.release") + "). Toque em Instalar / atualizar tudo.");
                    mostrarEstado();
                } catch (Exception e) {
                    caixa = null;
                    escrever("Sem root neste aparelho: " + e.getMessage());
                }
            }
        });
    }

    void conectar() {
        final String ip = lido(campoBox);
        if (ip.length() == 0) { escrever("Digite o IP da TV box."); return; }
        fila.submit(new Runnable() {
            public void run() {
                try {
                    if (adb != null) adb.fechar();
                    escrever("Conectando em " + ip + "…");
                    KeyPair k = Adb.chave(getFilesDir());
                    adb = new Adb(ip, k, new Adb.Aviso() { public void aviso(String s) { escrever(s); } });
                    caixa = new Caixa(adb, getAssets(), new Adb.Aviso() { public void aviso(String s) { escrever(s); } });
                    boxConectada = ip;
                    escrever("Conectado: " + caixa.sh("getprop ro.product.model") + " (Android "
                            + caixa.sh("getprop ro.build.version.release") + ")");
                    mostrarEstado();
                } catch (Exception e) {
                    escrever("Não conectou: " + e.getMessage());
                    if (e instanceof java.net.ConnectException || e instanceof java.net.SocketTimeoutException) escrever(AJUDA_ADB);
                }
            }
        });
    }

    void procurar() {
        escrever("Procurando TV boxes (porta 5555)…");
        new Thread(new Runnable() {
            public void run() {
                final List<String> ips = Collections.synchronizedList(new ArrayList<String>());
                ExecutorService ex = Executors.newFixedThreadPool(48);
                for (String prefixo : prefixos()) {
                    for (int i = 1; i < 255; i++) {
                        final String ip = prefixo + i;
                        ex.submit(new Runnable() {
                            public void run() {
                                Socket s = new Socket();
                                try {
                                    s.connect(new InetSocketAddress(ip, 5555), 400);
                                    ips.add(ip);
                                } catch (Exception e) {
                                } finally {
                                    try { s.close(); } catch (Exception e) { }
                                }
                            }
                        });
                    }
                }
                ex.shutdown();
                final String henbox = Descobridor.chamar();   // box que já tem o PS2 Henbox responde na hora
                if (henbox != null) escrever("PS2 Henbox já instalado na TV box " + henbox);
                try { ex.awaitTermination(60, TimeUnit.SECONDS); } catch (InterruptedException e) { }
                ui.post(new Runnable() {
                    public void run() {
                        achadas.removeAllViews();
                        if (ips.isEmpty()) { escrever("Nenhuma TV box com ADB pela rede encontrada."); escrever(AJUDA_ADB); }
                        for (final String ip : ips) {
                            botao(achadas, "TV box em " + ip + (ip.equals(henbox) ? " (PS2 Henbox)" : ""), new Runnable() { public void run() { campoBox.setText(ip); conectar(); } });
                        }
                    }
                });
            }
        }).start();
    }

    /** Redes /24 das interfaces do celular (Wi-Fi), ex.: "192.168.4.". */
    static List<String> prefixos() {
        List<String> r = new ArrayList<String>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (!(a instanceof Inet4Address)) continue;
                    String h = a.getHostAddress();
                    String p = h.substring(0, h.lastIndexOf('.') + 1);
                    if (!r.contains(p)) r.add(p);
                }
            }
        } catch (Exception e) { }
        return r;
    }

    /** henbox://parear?url=…&chave=… (QR do servidor/instalar.sh): preenche o servidor e, com uma box conectada, salva. */
    void parear(android.net.Uri u) {
        final String url = u.getQueryParameter("url"), chave = u.getQueryParameter("chave");
        if (url == null || chave == null) return;
        campoServidor.setText(url);
        campoChave.setText(chave);
        escrever("Servidor em nuvem lido do QR: " + url);
        if (caixa == null) { escrever("Conecte na TV box e toque em Salvar servidor na TV box."); return; }
        tarefa(new Tarefa() { public void rodar() throws Exception {
            caixa.configurarServidor(url, chave);
            escrever("Servidor salvo na TV box. Reiniciando os serviços…");
            caixa.iniciar(); caixa.esperar(20000); mostrarEstado(); } });
    }

    // ---- 🎵 música da loja: escolhe no celular e envia à pasta MUSICAS do pendrive da box (24/10/2026) ----
    android.net.Uri musicaUri = null;
    String musicaNome = "";

    void escolherMusica() {
        if (caixa == null) { escrever("Conecte numa TV box primeiro."); return; }
        android.content.Intent i = new android.content.Intent(android.content.Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(android.content.Intent.CATEGORY_OPENABLE);
        i.setType("audio/*");
        i.putExtra(android.content.Intent.EXTRA_MIME_TYPES,
                new String[] {"audio/*", "application/ogg", "application/octet-stream"});
        try {
            startActivityForResult(i, 20);
        } catch (Exception e) {
            escrever("Não abriu o seletor de arquivos: " + e.getMessage());
        }
    }

    @Override
    protected void onActivityResult(int req, int res, android.content.Intent data) {
        super.onActivityResult(req, res, data);
        if (req != 20 || res != RESULT_OK || data == null || data.getData() == null) return;
        musicaUri = data.getData();
        musicaNome = nomearMusica(musicaUri);
        tarefa(new Tarefa() { public void rodar() throws Exception { enviarMusica(); } });
    }

    /** Nome do arquivo como o usuário o tem (OpenableColumns.DISPLAY_NAME); sem ele, o fim do URL. */
    String nomearMusica(android.net.Uri u) {
        try {
            android.database.Cursor c = getContentResolver().query(u,
                    new String[] {android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (c != null) {
                if (c.moveToFirst()) {
                    String n = c.getString(0);
                    c.close();
                    if (n != null && n.trim().length() > 0) return n;
                } else {
                    c.close();
                }
            }
        } catch (Exception e) { }
        return u.getLastPathSegment() == null ? "musica.mp3" : u.getLastPathSegment();
    }

    /** Manda o arquivo (o Caixa copia ao pendrive como root) e pede à box para converter na hora. */
    void enviarMusica() throws Exception {
        String destino;
        java.io.InputStream in = getContentResolver().openInputStream(musicaUri);
        if (in == null) throw new java.io.IOException("não abri a música (formato ou permissão)");
        try {
            escrever("🎵 Enviando " + musicaNome + " para " + boxConectada + "…");
            destino = caixa.enviarMusica(musicaNome, in);
        } finally {
            in.close();
        }
        escrever("🎵 Gravada em " + destino + ". Convertendo…");
        String r = pedirHttp("http://" + ipBox() + ":8780/loja/api/musica?acao=atualizar");
        try {
            JSONObject j = new JSONObject(r.substring(r.indexOf('{')));
            JSONObject f = j.optJSONObject("faixa");
            escrever("🎵 Loja: " + (j.opt("total") != null ? j.getInt("total") : 0) + " faixa(s) · " + (f != null ? f.optString("titulo") : "sem faixa")
                    + (j.optBoolean("ligada") ? "" : " (desligada — toque o 🔈 na loja)"));
        } catch (Exception e) {
            escrever("🎵 A box converte sozinha em até 10 min. (confirmei falhou: " + e.getMessage() + ")");
        }
    }

    /** IP para a página da box: o do ADB, ou ela mesma se o app está rodando na TV box. */
    String ipBox() {
        return boxConectada.matches("\\d+\\.\\d+\\.\\d+\\.\\d+") ? boxConectada : "127.0.0.1";
    }

    String pedirHttp(String url) throws Exception {
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(300000);   // a conversão do ffmpeg (até 90 s de áudio) pode demorar na hora
        c.setRequestProperty("User-Agent", "ps2nav-apk/1.0");
        try {
            java.io.InputStream i = c.getResponseCode() >= 400 ? c.getErrorStream() : c.getInputStream();
            java.io.ByteArrayOutputStream b = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while (i != null && (n = i.read(buf)) > 0) b.write(buf, 0, n);
            if (i != null) i.close();
            return b.toString("UTF-8");
        } finally {
            c.disconnect();
        }
    }

    void listarPendrives() throws Exception {
        final String[] linhas = caixa.pendrives();
        ui.post(new Runnable() { public void run() {
            pendrives.removeAllViews();
            if (linhas.length == 0 || !linhas[0].contains("|")) {
                texto(pendrives, linhas.length > 0 ? linhas[0] : "Nenhum pendrive na USB da TV box. Espete um e toque de novo.");
                return;
            }
            for (String l : linhas) {
                final String[] c = l.split("\\|", -1);
                if (c.length < 4) continue;
                final boolean temIso = c[3].equals("sim");
                texto(pendrives, "Pendrive " + c[0] + ": " + c[1] + " MB, " + c[2] + " MB livres" + (temIso ? " · tem jogos (ISO)" : "")
                        + (c.length > 4 && c[4].trim().length() > 0 ? "\nPastas: " + c[4].trim() : ""));
                botao(pendrives, "Copiar o PS2 Henbox para " + c[0] + " (não apaga nada)", new Runnable() { public void run() {
                    tarefa(new Tarefa() { public void rodar() throws Exception {
                        escrever("Pendrive: " + caixa.prepararPendrive(c[0], false)); } }); } });
                if (!temIso) botao(pendrives, "Formatar " + c[0] + " (APAGA TUDO) e preparar", new Runnable() { public void run() {
                    new android.app.AlertDialog.Builder(Principal.this).setTitle("Apagar o pendrive " + c[0] + "?")
                        .setMessage("Tudo o que estiver nele (" + c[1] + " MB) será apagado e ele vira FAT32 com o PS2 Henbox.")
                        .setNegativeButton("Cancelar", null)
                        .setPositiveButton("Apagar e preparar", new android.content.DialogInterface.OnClickListener() {
                            public void onClick(android.content.DialogInterface d, int w) { tarefa(new Tarefa() {
                                public void rodar() throws Exception {
                                    escrever("Pendrive: " + caixa.prepararPendrive(c[0], true)); } }); } }).show(); } });
            }
        } });
    }

    /** Central do celular (24/10/2026): a página do central.py da box num WebView (Central.java). */
    void abrirCentral() {
        android.content.Intent i = new android.content.Intent(this, Central.class);
        if (boxConectada.matches("\\d+\\.\\d+\\.\\d+\\.\\d+")) i.putExtra("box", boxConectada);
        else if (boxConectada.equals("esta TV box")) i.putExtra("box", "127.0.0.1");
        else if (!Conquistas.tvbox(this).isEmpty()) i.putExtra("box", Conquistas.tvbox(this));
        startActivity(i);
    }

    void abrirConquistas() {
        android.content.Intent i = new android.content.Intent(this, Conquistas.class);
        String ip = boxConectada.matches("\\d+\\.\\d+\\.\\d+\\.\\d+") ? boxConectada : "";
        if (ip.length() > 0 && Conquistas.tvbox(this).isEmpty())
            Conquistas.prefs(this).edit().putString("tvbox", ip).apply();
        startActivity(i);
    }

    void mostrarChecklist() throws Exception {
        String bruto = caixa.checklist();
        final StringBuilder sb = new StringBuilder("TV box " + boxConectada + "\n");
        try {
            org.json.JSONArray a = new org.json.JSONArray(bruto.substring(bruto.indexOf('[')));
            int faltam = 0;
            for (int k = 0; k < a.length(); k++) {
                JSONObject i = a.getJSONObject(k);
                Object ok = i.opt("ok");
                String sinal = Boolean.TRUE.equals(ok) ? "✅" : Boolean.FALSE.equals(ok) ? "❌" : "➖";
                if (Boolean.FALSE.equals(ok)) faltam++;
                sb.append(sinal).append(' ').append(i.optString("item")).append(": ").append(i.optString("detalhe")).append('\n');
                if (i.optString("resolver").length() > 0) sb.append("   👉 ").append(i.optString("resolver")).append('\n');
            }
            sb.append(faltam == 0 ? "\nTudo certo! ➖ = opcional ou PS2 desligado." : "\n" + faltam + " item(ns) a resolver.");
        } catch (Exception e) {
            sb.append("Estado indisponível (instale ou atualize primeiro):\n").append(bruto.length() > 300 ? bruto.substring(0, 300) : bruto);
        }
        ui.post(new Runnable() { public void run() { estado.setText(sb.toString()); } });
    }

    void mostrarEstado() throws Exception {
        String bruto = caixa.estado();
        final StringBuilder sb = new StringBuilder();
        try {
            JSONObject j = new JSONObject(bruto.substring(bruto.indexOf('{')));
            JSONObject ps2 = j.getJSONObject("ps2"), sv = j.getJSONObject("servicos");
            sb.append("TV box ").append(boxConectada).append(" · ").append(j.optString("hora")).append('\n');
            sb.append("Versão: ").append(j.optString("versao", "?")).append('\n');
            sb.append("PS2 ").append(ps2.optString("ip")).append(": ")
              .append(ps2.optBoolean("responde_ping") ? "responde na rede" : "não responde").append('\n');
            sb.append("Navegador no PS2: ").append(ps2.optString("navegador")).append('\n');
            sb.append("Última conexão: ").append(ps2.optString("ultima_conexao")).append('\n');
            sb.append("Serviços: ");
            String[] nomes = {"servidor_host.py", "navegador_servidor.py", "videos.py", "udpfs_nuvem.py"};
            for (String n : nomes) sb.append(sv.optBoolean(n) ? "✔ " : "✘ ").append(n.replace(".py", "")).append("  ");
            sb.append('\n');
            sb.append("WebView: ").append(j.optBoolean("webview") ? "ok" : "parado").append(" · página: ")
              .append(j.optBoolean("pagina") ? "ok" : "parada").append('\n');
            sb.append("Servidor em nuvem: ").append(j.optString("notebook")).append('\n');
            sb.append("Espaço livre: ").append(j.optLong("espaco_livre_mb")).append(" MB\n");
            final String ip = ps2.optString("ip");
            ui.post(new Runnable() { public void run() { if (ip.length() > 0) campoIp.setText(ip); } });
        } catch (Exception e) {
            sb.append("Estado indisponível (instale primeiro):\n").append(bruto.length() > 300 ? bruto.substring(0, 300) : bruto);
        }
        ui.post(new Runnable() { public void run() { estado.setText(sb.toString()); } });
    }

    // ---------- tela ----------
    int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }

    TextView titulo(LinearLayout pai, String s, int tam) {
        TextView t = texto(pai, s);
        t.setTextSize(tam);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(0, dp(14), 0, dp(6));
        return t;
    }

    TextView texto(LinearLayout pai, String s) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(14);
        t.setPadding(0, dp(4), 0, dp(4));
        pai.addView(t, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return t;
    }

    Button botao(LinearLayout pai, String s, final Runnable acao) {
        Button bt = new Button(this);
        bt.setText(s);
        bt.setAllCaps(false);
        bt.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { acao.run(); } });
        pai.addView(bt, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return bt;
    }

    EditText campo(LinearLayout pai, String dica, String valor) {
        EditText e = new EditText(this);
        e.setHint(dica);
        e.setText(valor);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_PHONE);
        pai.addView(e, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return e;
    }

    String lido(EditText e) { return e.getText().toString().trim(); }

    void escrever(final String s) {
        // também em arquivo (o logcat de algumas boxes vem desligado): files/registro.txt, lido pelo ADB com su
        try {
            java.io.FileWriter f = new java.io.FileWriter(new java.io.File(getFilesDir(), "registro.txt"), true);
            f.write(new java.text.SimpleDateFormat("HH:mm:ss").format(new java.util.Date()) + " " + s + "\n");
            f.close();
        } catch (Exception e) { }
        ui.post(new Runnable() {
            public void run() {
                log.append(s + "\n");
            }
        });
    }
}
