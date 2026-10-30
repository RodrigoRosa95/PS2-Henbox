package br.ps2nav;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.wifi.SupplicantState;
import android.net.wifi.WifiConfiguration;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.IBinder;
import android.util.Log;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;

/**
 * Wi-Fi da TV box pelo navegador do PS2 (pedido do usuário 23/10/2026). O videos.py (página 📶 Wi-Fi) busca as redes
 * pelo iw e chama este serviço como root:
 *   am startservice -n br.ps2nav/.Wifi --es ssid NOME --es senha SENHA
 * Conecta pelo WifiManager (o app mira o SDK 23, então addNetwork/enableNetwork ainda valem no Android 10) e espera
 * até 60 s por IP. Não deu: apaga a rede nova e volta para a anterior, para a box não ficar sem Wi-Fi.
 * Cada passo vai ao videos.py em POST 127.0.0.1:8780/wifi/resposta {"estado", "ssid", "msg"}.
 */
public class Wifi extends Service {
    static final String TAG = "ps2nav-wifi";
    static final int ESPERA_S = 60;
    static volatile boolean ocupado = false;

    @Override
    public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent i, int flags, int id) {
        final String ssid = i == null ? null : i.getStringExtra("ssid");
        final String senha = i == null ? "" : i.getStringExtra("senha");
        if (ssid == null || ssid.isEmpty()) { stopSelf(id); return START_NOT_STICKY; }
        if (ocupado) { avisar("erro", ssid, "já estou trocando de rede, espere terminar"); return START_NOT_STICKY; }
        ocupado = true;
        final int pedido = id;
        new Thread(new Runnable() {
            public void run() {
                try {
                    conectar(ssid, senha == null ? "" : senha);
                } catch (Exception e) {
                    Log.e(TAG, "conectar", e);
                    avisar("erro", ssid, "erro no Android: " + e);
                } finally {
                    ocupado = false;
                    stopSelf(pedido);
                }
            }
        }).start();
        return START_NOT_STICKY;
    }

    void conectar(String ssid, String senha) throws InterruptedException {
        WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        if (!wm.isWifiEnabled()) wm.setWifiEnabled(true);
        WifiInfo atual = wm.getConnectionInfo();
        int anterior = atual == null ? -1 : atual.getNetworkId();
        String aspas = "\"" + ssid + "\"";
        int velha = -1;   // a mesma rede já salva (senha antiga): sai e entra a nova, mas só some se a nova der certo
        List<WifiConfiguration> salvas = wm.getConfiguredNetworks();
        if (salvas != null)
            for (WifiConfiguration c : salvas) if (aspas.equals(c.SSID)) velha = c.networkId;
        boolean salva = senha.isEmpty() && velha >= 0;   // senha em branco numa rede salva: usa a senha que já está lá
        if (salva && velha == anterior) {
            avisar("ok", ssid, "já conectada");
            return;
        }
        int nova = velha;
        if (!salva) {
            WifiConfiguration c = new WifiConfiguration();
            c.SSID = aspas;
            if (senha.isEmpty()) {
                c.allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE);
            } else {
                c.preSharedKey = "\"" + senha + "\"";
            }
            nova = wm.addNetwork(c);
            if (nova < 0) { avisar("erro", ssid, "o Android recusou a rede"); return; }
        }
        avisar("conectando", ssid, "conectando…");
        wm.disconnect();
        wm.enableNetwork(nova, true);   // true: desliga as outras por enquanto, senão o Android volta para a antiga
        wm.reconnect();
        for (int s = 0; s < ESPERA_S; s++) {
            Thread.sleep(1000);
            WifiInfo w = wm.getConnectionInfo();
            if (w != null && w.getNetworkId() == nova && w.getSupplicantState() == SupplicantState.COMPLETED
                    && w.getIpAddress() != 0) {
                if (velha >= 0 && velha != nova) wm.removeNetwork(velha);
                religarTodas(wm);
                wm.saveConfiguration();
                avisar("ok", ssid, "conectada, IP " + ip(w.getIpAddress()));
                return;
            }
        }
        // não conectou: tira a nova (a salva fica) e volta para a anterior
        if (!salva) wm.removeNetwork(nova);
        religarTodas(wm);
        if (anterior >= 0) wm.enableNetwork(anterior, true);
        wm.reconnect();
        wm.saveConfiguration();
        if (anterior >= 0) {   // a anterior também foi desligada pelo enableNetwork(…, true): religa de novo
            Thread.sleep(15000);
            religarTodas(wm);
        }
        avisar("erro", ssid, "não conectou em " + ESPERA_S + " s (senha errada ou sinal fraco); voltei para a rede anterior");
    }

    static void religarTodas(WifiManager wm) {
        List<WifiConfiguration> salvas = wm.getConfiguredNetworks();
        if (salvas != null) for (WifiConfiguration c : salvas) wm.enableNetwork(c.networkId, false);
    }

    static String ip(int n) {
        return (n & 0xff) + "." + ((n >> 8) & 0xff) + "." + ((n >> 16) & 0xff) + "." + ((n >> 24) & 0xff);
    }

    static String json(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char ch : s.toCharArray()) {
            if (ch == '"' || ch == '\\') b.append('\\').append(ch);
            else if (ch < 0x20) b.append(String.format("\\u%04x", (int) ch));
            else b.append(ch);
        }
        return b.append('"').toString();
    }

    static void avisar(String estado, String ssid, String msg) {
        Log.i(TAG, estado + " " + ssid + ": " + msg);
        try {
            HttpURLConnection h = (HttpURLConnection) new URL("http://127.0.0.1:8780/wifi/resposta").openConnection();
            h.setRequestMethod("POST");
            h.setDoOutput(true);
            h.setConnectTimeout(3000);
            h.setReadTimeout(3000);
            h.setRequestProperty("Content-Type", "application/json");
            byte[] corpo = ("{\"estado\":" + json(estado) + ",\"ssid\":" + json(ssid) + ",\"msg\":" + json(msg) + "}")
                    .getBytes("UTF-8");
            try (OutputStream o = h.getOutputStream()) { o.write(corpo); }
            h.getResponseCode();
            h.disconnect();
        } catch (Exception e) {
            Log.w(TAG, "aviso ao videos.py: " + e);
        }
    }
}
