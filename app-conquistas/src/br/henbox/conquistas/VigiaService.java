package br.henbox.conquistas;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.AudioAttributes;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Vigia em primeiro plano: a cada 5 s pergunta à TV box (videos.py, /conquistas/api/desbloqueios?desde=) e notifica
 * cada conquista nova com a medalha, o nome, os pontos e o plim de troféu (res/raw/trofeu.wav). Fora de casa a TV box
 * não responde e ele só espera. Compilado com o SDK 23: canal de notificação (Android 8+) por reflexão.
 */
public class VigiaService extends Service {
    static final String CANAL = "conquistas";
    static final int ID_FIXA = 1;
    volatile boolean rodando;

    static Uri som(Context c) {
        int id = c.getResources().getIdentifier("trofeu", "raw", c.getPackageName());   // sem R.java neste build
        return Uri.parse("android.resource://" + c.getPackageName() + "/" + id);
    }

    /** Canal com o plim (Android 8+). No 13, criar o 1º canal é o que faz o sistema pedir a permissão. */
    static void criarCanal(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        try {
            Class<?> canal = Class.forName("android.app.NotificationChannel");
            Object ch = canal.getConstructor(String.class, CharSequence.class, int.class)
                    .newInstance(CANAL, "Conquistas desbloqueadas", 4 /* IMPORTANCE_HIGH */);
            canal.getMethod("setDescription", String.class).invoke(ch, "Uma notificação por conquista do PS2");
            AudioAttributes aa = new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
            canal.getMethod("setSound", Uri.class, AudioAttributes.class).invoke(ch, som(c), aa);
            canal.getMethod("enableVibration", boolean.class).invoke(ch, true);
            NotificationManager nm = (NotificationManager) c.getSystemService(NOTIFICATION_SERVICE);
            nm.getClass().getMethod("createNotificationChannel", canal).invoke(nm, ch);
        } catch (Exception ignorado) {
        }
    }

    static Notification.Builder construtor(Context c) {
        if (Build.VERSION.SDK_INT >= 26) {
            try {
                return Notification.Builder.class.getConstructor(Context.class, String.class).newInstance(c, CANAL);
            } catch (Exception ignorado) {
            }
        }
        return new Notification.Builder(c);
    }

    @Override
    public int onStartCommand(Intent i, int flags, int id) {
        criarCanal(this);
        PendingIntent abrir = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | 0x04000000 /* FLAG_IMMUTABLE, exigido no Android 12+ */);
        Notification fixa = construtor(this).setSmallIcon(android.R.drawable.star_on)
                .setContentTitle("PS2 Conquistas").setContentText("Vigiando as conquistas do PS2")
                .setContentIntent(abrir).setOngoing(true).setPriority(Notification.PRIORITY_MIN).build();
        startForeground(ID_FIXA, fixa);
        if (!rodando) {
            rodando = true;
            new Thread() { public void run() { vigiar(); } }.start();
        }
        return START_STICKY;
    }

    void vigiar() {
        while (rodando) {
            try {
                String ip = MainActivity.tvbox(this);
                if (!ip.isEmpty()) verificar(ip);
            } catch (Exception foraDeCasa) {
            }
            try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
        }
    }

    void verificar(String ip) throws Exception {
        long desde = MainActivity.prefs(this).getLong("desde", 0);
        boolean primeira = desde == 0;   // 1ª vez: marca o ponto de partida sem notificar o histórico antigo
        JSONArray a = new JSONArray(texto("http://" + ip + ":8780/conquistas/api/desbloqueios?desde=" + desde));
        long maior = primeira ? System.currentTimeMillis() / 1000 : desde;
        for (int k = 0; k < a.length(); k++) {
            JSONObject d = a.getJSONObject(k);
            long quando = (long) Math.ceil(d.optDouble("quando", 0));
            if (quando > maior) maior = quando;
            if (!primeira) notificar(ip, d);
        }
        MainActivity.prefs(this).edit().putLong("desde", maior).apply();
    }

    void notificar(String ip, JSONObject d) {
        Bitmap medalha = null;
        try {
            byte[] png = bytes("http://" + ip + ":8780/conquistas/medalha/" + d.optString("medalha") + ".png");
            medalha = BitmapFactory.decodeByteArray(png, 0, png.length);
        } catch (Exception ignorado) {
        }
        String texto = d.optString("titulo") + " · +" + d.optInt("pontos") + " pts";
        PendingIntent abrir = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | 0x04000000);
        Notification.Builder n = construtor(this).setSmallIcon(android.R.drawable.star_big_on)
                .setContentTitle("🏆 Conquista desbloqueada")
                .setContentText(texto)
                .setStyle(new Notification.BigTextStyle().bigText(texto + "\n" + d.optString("descricao")
                        + (d.optString("jogo").isEmpty() ? "" : "\n" + d.optString("jogo"))))
                .setSound(som(this)).setVibrate(new long[]{0, 120, 80, 120})
                .setPriority(Notification.PRIORITY_HIGH).setAutoCancel(true).setContentIntent(abrir);
        if (medalha != null) n.setLargeIcon(medalha);
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(d.optInt("id", (int) System.currentTimeMillis()), n.build());
    }

    static byte[] bytes(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(8000);
        InputStream in = c.getInputStream();
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
        in.close();
        return b.toByteArray();
    }

    static String texto(String url) throws Exception {
        return new String(bytes(url), "UTF-8");
    }

    @Override
    public void onDestroy() {
        rodando = false;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) {
        return null;
    }
}
