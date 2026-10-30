package br.ps2nav.instalador;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.wifi.WifiManager;
import android.os.Environment;
import android.os.IBinder;
import android.os.PowerManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * ISOs do celular para o PS2 (pedido do usuário 24/10/2026): procura .iso na memória do celular (e no cartão SD),
 * descobre o código de cada jogo pelo SYSTEM.CNF e serve por HTTP na porta 8786 (com Range e conexão mantida, que o
 * udpfs_nuvem.py da TV box usa para ler aos pedaços enquanto o PS2 joga). Só responde a quem manda a chave
 * (X-Chave), que a box recebe no registro feito pela página da Central. Fica em primeiro plano, com o Wi-Fi e o
 * processador acordados, até tocar em "Parar" na notificação.
 */
public class ServidorIsos extends Service {
    static final int PORTA = 8786, ID_FIXA = 2;
    static final String PARAR = "parar";
    static final Pattern CODIGO = Pattern.compile("([A-Z]{4})[_-](\\d{3})\\.?(\\d{2})");
    static volatile List<File> isos = new ArrayList<File>();
    static volatile List<String> codigos = new ArrayList<String>();
    static String chave;
    static volatile boolean ligado;
    ServerSocket srv;
    PowerManager.WakeLock acordado;
    WifiManager.WifiLock wifi;

    static synchronized String chave() {
        if (chave == null) {
            byte[] b = new byte[18];
            new SecureRandom().nextBytes(b);
            chave = android.util.Base64.encodeToString(b, android.util.Base64.NO_WRAP | android.util.Base64.URL_SAFE);
        }
        return chave;
    }

    /** A chave fica guardada: o serviço reaberto pelo sistema continua valendo para a box já registrada. */
    static synchronized void carregarChave(Context c) {
        android.content.SharedPreferences p = c.getSharedPreferences("isos", MODE_PRIVATE);
        chave = p.getString("chave", null);
        if (chave == null) p.edit().putString("chave", chave()).apply();
    }

    // ---------- procura ----------
    /** Pastas onde procurar: memória interna e cartões SD/pendrives em /storage. */
    static List<File> raizes() {
        List<File> r = new ArrayList<File>();
        r.add(Environment.getExternalStorageDirectory());
        File[] st = new File("/storage").listFiles();
        if (st != null) for (File f : st) {
            String n = f.getName();
            if (!n.equals("emulated") && !n.equals("self") && f.isDirectory() && f.canRead()) r.add(f);
        }
        return r;
    }

    static void varrer(File d, int nivel, List<File> achados, Set<String> nomes) {
        if (nivel > 7 || achados.size() >= 500) return;
        File[] fs = d.listFiles();
        if (fs == null) return;
        for (File f : fs) {
            String n = f.getName();
            if (n.startsWith(".")) continue;
            if (f.isDirectory()) {
                if (nivel == 0 && n.equals("Android")) continue;   // dados dos apps
                varrer(f, nivel + 1, achados, nomes);
            } else if (n.toLowerCase(Locale.ROOT).endsWith(".iso") && f.length() > (1 << 20) && nomes.add(n)) {
                achados.add(f);
            }
        }
    }

    /** Procura de novo (bloqueia: rodar fora da tela). */
    static synchronized void procurar() {
        List<File> achados = new ArrayList<File>();
        Set<String> nomes = new HashSet<String>();
        for (File r : raizes()) varrer(r, 0, achados, nomes);
        List<String> cods = new ArrayList<String>();
        for (File f : achados) cods.add(codigoDe(f));
        isos = achados;
        codigos = cods;
    }

    /** Código do jogo (SLUS_203.12) pelo BOOT2 do SYSTEM.CNF; senão pelo nome do arquivo; "" se nenhum. */
    static String codigoDe(File iso) {
        RandomAccessFile f = null;
        try {
            f = new RandomAccessFile(iso, "r");
            byte[] pvd = ler(f, 16L * 2048, 2048);
            if (pvd[1] == 'C' && pvd[2] == 'D' && pvd[3] == '0') {
                long setor = u32(pvd, 156 + 2), tam = u32(pvd, 156 + 10);
                byte[] dir = ler(f, setor * 2048, (int) Math.min(tam, 64 * 1024));
                int p = 0;
                while (p < dir.length) {
                    int n = dir[p] & 0xFF;
                    if (n == 0) { p = (p / 2048 + 1) * 2048; continue; }
                    int ln = dir[p + 32] & 0xFF;
                    String nome = new String(dir, p + 33, ln, "ISO-8859-1").toUpperCase(Locale.ROOT);
                    if (nome.startsWith("SYSTEM.CNF")) {
                        byte[] cnf = ler(f, u32(dir, p + 2) * 2048, (int) Math.min(u32(dir, p + 10), 2047));
                        Matcher m = CODIGO.matcher(new String(cnf, "ISO-8859-1").toUpperCase(Locale.ROOT));
                        if (m.find()) return m.group(1) + "_" + m.group(2) + "." + m.group(3);
                        break;
                    }
                    p += n;
                }
            }
        } catch (Exception ignorado) {
        } finally {
            try { if (f != null) f.close(); } catch (Exception e) { }
        }
        Matcher m = CODIGO.matcher(iso.getName().toUpperCase(Locale.ROOT));
        return m.lookingAt() ? m.group(1) + "_" + m.group(2) + "." + m.group(3) : "";
    }

    static byte[] ler(RandomAccessFile f, long pos, int n) throws Exception {
        byte[] b = new byte[n];
        f.seek(pos);
        f.readFully(b);
        return b;
    }

    static long u32(byte[] b, int p) {
        return (b[p] & 0xFFL) | (b[p + 1] & 0xFFL) << 8 | (b[p + 2] & 0xFFL) << 16 | (b[p + 3] & 0xFFL) << 24;
    }

    static String lista() throws Exception {
        JSONArray a = new JSONArray();
        List<File> fs = isos;
        List<String> cs = codigos;
        for (int i = 0; i < fs.size(); i++) {
            File f = fs.get(i);
            a.put(new JSONObject().put("i", i).put("nome", f.getName()).put("tam", f.length())
                    .put("codigo", cs.get(i)).put("pasta", f.length() < 750L << 20 ? "CD" : "DVD")
                    .put("caminho", f.getParent()));
        }
        return new JSONObject().put("aparelho", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL)
                .put("isos", a).toString();
    }

    /** IPv4 do celular na rede local (de preferência na mesma faixa da TV box). */
    static String meuIp(String box) {
        String pre = box != null && box.lastIndexOf('.') > 0 ? box.substring(0, box.lastIndexOf('.') + 1) : null, outro = null;
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (!(a instanceof Inet4Address) || !a.isSiteLocalAddress()) continue;
                    String ip = a.getHostAddress();
                    if (pre != null && ip.startsWith(pre)) return ip;
                    if (outro == null) outro = ip;
                }
            }
        } catch (Exception ignorado) {
        }
        return outro;
    }

    // ---------- serviço ----------
    @Override
    public int onStartCommand(Intent i, int flags, int id) {
        if (i != null && PARAR.equals(i.getAction())) {
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        carregarChave(this);
        if (isos.isEmpty()) new Thread(new Runnable() { public void run() { procurar(); } }).start();
        VigiaConquistas.criarCanal(this);
        PendingIntent parar = PendingIntent.getService(this, 1, new Intent(this, ServidorIsos.class).setAction(PARAR),
                PendingIntent.FLAG_UPDATE_CURRENT | 0x04000000 /* FLAG_IMMUTABLE */);
        Notification n = VigiaConquistas.construtor(this).setSmallIcon(android.R.drawable.stat_sys_upload)
                .setContentTitle("PS2 Henbox").setContentText("Servindo os ISOs deste celular para o PS2 (toque para parar)")
                .setContentIntent(parar).setOngoing(true).setPriority(Notification.PRIORITY_LOW).build();
        startForeground(ID_FIXA, n);
        if (srv == null) {
            try {
                acordado = ((PowerManager) getSystemService(Context.POWER_SERVICE))
                        .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "henbox:isos");
                acordado.acquire();
                wifi = ((WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE))
                        .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "henbox:isos");
                wifi.acquire();
            } catch (Exception ignorado) {
            }
            new Thread(new Runnable() { public void run() { servir(); } }).start();
        }
        return START_STICKY;
    }

    void servir() {
        try {
            srv = new ServerSocket(PORTA);
            ligado = true;
            while (!srv.isClosed()) {
                final Socket s = srv.accept();
                new Thread(new Runnable() { public void run() { conversa(s); } }).start();
            }
        } catch (Exception ignorado) {
        } finally {
            ligado = false;
        }
    }

    /** Uma conexão: vários pedidos seguidos (HTTP/1.1 mantido), GET/HEAD de /lista e /iso/<n>/<nome>. */
    static void conversa(Socket s) {
        try {
            s.setSoTimeout(120000);
            s.setTcpNoDelay(true);
            InputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();
            while (true) {
                String linha = linha(in);
                if (linha == null || linha.length() == 0) break;
                String chaveRecebida = "", range = "";
                for (String h; (h = linha(in)) != null && h.length() > 0; ) {
                    int dp = h.indexOf(':');
                    if (dp < 0) continue;
                    String nome = h.substring(0, dp).trim().toLowerCase(Locale.ROOT), valor = h.substring(dp + 1).trim();
                    if (nome.equals("x-chave")) chaveRecebida = valor;
                    else if (nome.equals("range")) range = valor;
                }
                String[] p = linha.split(" ");
                if (p.length < 2) break;
                boolean cabeca = p[0].equals("HEAD");
                String caminho = p[1];
                if (!chave().equals(chaveRecebida)) { resposta(out, 403, "text/plain", "chave".getBytes(), cabeca); continue; }
                if (caminho.equals("/lista")) { resposta(out, 200, "application/json", lista().getBytes("UTF-8"), cabeca); continue; }
                Matcher m = Pattern.compile("^/iso/(\\d+)/.*").matcher(caminho);
                List<File> fs = isos;
                int n = m.matches() ? Integer.parseInt(m.group(1)) : -1;
                if (n < 0 || n >= fs.size()) { resposta(out, 404, "text/plain", "não encontrado".getBytes("UTF-8"), cabeca); continue; }
                File f = fs.get(n);
                String pedido = URLDecoder.decode(caminho.substring(caminho.indexOf('/', 5) + 1), "UTF-8");
                if (!pedido.equals(f.getName())) { resposta(out, 404, "text/plain", "lista mudou".getBytes(), cabeca); continue; }
                long tam = f.length(), ini = 0, fim = tam - 1;
                Matcher r = Pattern.compile("bytes=(\\d+)-(\\d*)").matcher(range);
                boolean parcial = r.find();
                if (parcial) {
                    ini = Long.parseLong(r.group(1));
                    if (r.group(2).length() > 0) fim = Math.min(fim, Long.parseLong(r.group(2)));
                }
                if (ini > fim) { resposta(out, 416, "text/plain", new byte[0], cabeca); continue; }
                StringBuilder cab = new StringBuilder();
                cab.append(parcial ? "HTTP/1.1 206 Partial Content\r\n" : "HTTP/1.1 200 OK\r\n")
                        .append("Content-Type: application/octet-stream\r\nAccept-Ranges: bytes\r\n")
                        .append("Content-Length: ").append(fim - ini + 1).append("\r\n");
                if (parcial) cab.append("Content-Range: bytes ").append(ini).append('-').append(fim).append('/').append(tam).append("\r\n");
                out.write(cab.append("\r\n").toString().getBytes("UTF-8"));
                if (!cabeca) {
                    RandomAccessFile a = new RandomAccessFile(f, "r");
                    try {
                        a.seek(ini);
                        byte[] b = new byte[256 * 1024];
                        long falta = fim - ini + 1;
                        while (falta > 0) {
                            int k = a.read(b, 0, (int) Math.min(b.length, falta));
                            if (k < 0) break;
                            out.write(b, 0, k);
                            falta -= k;
                        }
                    } finally {
                        a.close();
                    }
                }
                out.flush();
            }
        } catch (Exception ignorado) {
        } finally {
            try { s.close(); } catch (Exception e) { }
        }
    }

    static String linha(InputStream in) throws Exception {
        StringBuilder sb = new StringBuilder();
        int c;
        while ((c = in.read()) >= 0) {
            if (c == '\n') return sb.toString().replace("\r", "");
            if (sb.length() < 8192) sb.append((char) c);
        }
        return sb.length() > 0 ? sb.toString() : null;
    }

    static void resposta(OutputStream out, int cod, String tipo, byte[] d, boolean cabeca) throws Exception {
        out.write(("HTTP/1.1 " + cod + (cod == 200 ? " OK" : " Erro") + "\r\nContent-Type: " + tipo
                + "\r\nContent-Length: " + d.length + "\r\n\r\n").getBytes("UTF-8"));
        if (!cabeca) out.write(d);
        out.flush();
    }

    @Override
    public void onDestroy() {
        try { if (srv != null) srv.close(); } catch (Exception e) { }
        srv = null;
        try { if (acordado != null) acordado.release(); } catch (Exception e) { }
        try { if (wifi != null) wifi.release(); } catch (Exception e) { }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) {
        return null;
    }
}
