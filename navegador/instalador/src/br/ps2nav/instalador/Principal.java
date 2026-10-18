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
    LinearLayout achadas;
    EditText campoBox, campoIp, campoMascara, campoGw, campoServidor, campoChave;
    TextView log, estado;
    Canal adb;
    Caixa caixa;
    String boxConectada = "";

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        ScrollView rolagem = new ScrollView(this);
        LinearLayout raiz = new LinearLayout(this);
        raiz.setOrientation(LinearLayout.VERTICAL);
        int m = dp(16);
        raiz.setPadding(m, m, m, m);
        rolagem.addView(raiz);
        setContentView(rolagem);

        titulo(raiz, "Instalador PS2 Navegador", 22);
        texto(raiz, "1. Conecte o celular no mesmo Wi-Fi da TV box (com ADB pela rede ligado). 2. Procure ou digite o IP. "
                + "3. Conecte e aceite \"Permitir depuração\" na TV.");
        botao(raiz, "Instalar NESTA TV box (este aparelho, com root)", new Runnable() { public void run() { conectarAqui(); } });
        texto(raiz, "Ou, do celular:");
        botao(raiz, "Procurar TV boxes na rede", new Runnable() { public void run() { procurar(); } });
        achadas = new LinearLayout(this);
        achadas.setOrientation(LinearLayout.VERTICAL);
        raiz.addView(achadas);
        campoBox = campo(raiz, "IP da TV box (ex.: 192.168.4.121)", "");
        botao(raiz, "Conectar", new Runnable() { public void run() { conectar(); } });

        titulo(raiz, "TV box", 18);
        botao(raiz, "Instalar / atualizar tudo", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { caixa.instalar(); mostrarEstado(); } }); } });
        botao(raiz, "Ver estado", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { mostrarEstado(); } }); } });
        botao(raiz, "Reiniciar serviços", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception { caixa.uidTermux = caixa.su("stat -c %u " + Caixa.T); caixa.iniciar();
                escrever("Serviços reiniciando (uns 20 s)…"); caixa.esperar(20000); mostrarEstado(); } }); } });
        estado = texto(raiz, "Estado: conecte numa TV box.");
        estado.setTypeface(Typeface.MONOSPACE);

        titulo(raiz, "Servidor em nuvem (opcional)", 18);
        texto(raiz, "O PC com a sua coleção (servidor/instalar.sh mostra o endereço e a chave). Sem ele, a TV box "
                + "mostra só os jogos e vídeos dela.");
        campoServidor = campo(raiz, "Endereço (ex.: http://192.168.0.10:8781)", "");
        campoChave = campo(raiz, "Chave", "");
        botao(raiz, "Salvar servidor na TV box", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception {
                caixa.configurarServidor(lido(campoServidor), lido(campoChave));
                escrever("Servidor salvo. Reiniciando os serviços…");
                caixa.iniciar(); caixa.esperar(20000); mostrarEstado(); } }); } });

        titulo(raiz, "PS2", 18);
        campoIp = campo(raiz, "IP do PS2", "192.168.4.230");
        campoMascara = campo(raiz, "Máscara", "255.255.255.0");
        campoGw = campo(raiz, "Gateway", "192.168.4.1");
        botao(raiz, "Salvar IP na TV box", new Runnable() { public void run() { tarefa(new Tarefa() {
            public void rodar() throws Exception {
                caixa.trocarIp(lido(campoIp), lido(campoMascara), lido(campoGw));
                escrever("IP salvo. Grave no pendrive do PS2 (abaixo) e reinicie os serviços."); } }); } });
        texto(raiz, "Com o navegador aberto no PS2 (pelo IP antigo):");
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
                try { ex.awaitTermination(60, TimeUnit.SECONDS); } catch (InterruptedException e) { }
                ui.post(new Runnable() {
                    public void run() {
                        achadas.removeAllViews();
                        if (ips.isEmpty()) { escrever("Nenhuma TV box com ADB pela rede encontrada."); escrever(AJUDA_ADB); }
                        for (final String ip : ips) {
                            botao(achadas, "TV box em " + ip, new Runnable() { public void run() { campoBox.setText(ip); conectar(); } });
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
        ui.post(new Runnable() {
            public void run() {
                log.append(s + "\n");
            }
        });
    }
}
