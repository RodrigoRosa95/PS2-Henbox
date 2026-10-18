package br.ps2nav;

import android.app.Notification;
import android.app.Presentation;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;
import android.view.Gravity;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * Navegador do PS2 na TV box (pedido do usuário 17/10/2026: tirar a parte do Chrome do notebook).
 * Um WebView desenhado numa tela virtual 640x448 que ninguém vê (o navegador_servidor.py manda nele pelo DevTools,
 * como fazia com o Chrome sem janela) + uma ponte TCP 127.0.0.1:9222 → socket do DevTools do WebView
 * (@webview_devtools_remote_<pid>, que só aceita o próprio app). O Termux conecta na 9222.
 * Se a tela virtual não funcionar, cai para uma janela sobreposta transparente.
 * A imagem da tela virtual também sai crua em 127.0.0.1:9223 (o Page.captureScreenshot do WebView 74 não entrega
 * quadro nessa tela): cada conexão recebe "PSW1" num:u32 larg:u16 alt:u16 + larg*alt*4 bytes RGBA (último quadro).
 */
public class Servico extends Service {
    static final String TAG = "ps2nav";
    static final int LARG = 640, ALT = 448, PORTA = 9222, PORTA_QUADRO = 9223;
    static final byte[] quadro = new byte[LARG * ALT * 4];
    static volatile int num_quadro = 0;
    static WebView web;
    VirtualDisplay tela;
    ImageReader leitor;
    Presentation apresentacao;
    PowerManager.WakeLock trava;

    @Override
    public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent i, int flags, int id) {
        if (web == null) iniciar();
        return START_STICKY;
    }

    void iniciar() {
        Notification n = new Notification.Builder(this).setContentTitle("PS2 Navegador")
                .setContentText("página do PS2 rodando").setSmallIcon(android.R.drawable.ic_menu_view).build();
        startForeground(1, n);
        trava = ((PowerManager) getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ps2nav");
        trava.acquire();
        WebView.setWebContentsDebuggingEnabled(true);
        CookieManager.getInstance().setAcceptCookie(true);
        try {
            telaVirtual();
        } catch (Throwable e) {
            Log.w(TAG, "tela virtual falhou, usando janela sobreposta", e);
            sobreposta();
        }
        new Thread(new Runnable() { public void run() { ponte(); } }).start();
        new Thread(new Runnable() { public void run() { servirQuadros(); } }).start();
    }

    /** 127.0.0.1:9223: uma conexão = um quadro (cabeçalho + RGBA). */
    void servirQuadros() {
        try {
            ServerSocket srv = new ServerSocket(PORTA_QUADRO, 8, InetAddress.getByName("127.0.0.1"));
            byte[] copia = new byte[quadro.length];
            while (true) {
                Socket c = srv.accept();
                try {
                    int num;
                    synchronized (quadro) { System.arraycopy(quadro, 0, copia, 0, quadro.length); num = num_quadro; }
                    byte[] cab = new byte[12];
                    cab[0] = 'P'; cab[1] = 'S'; cab[2] = 'W'; cab[3] = '1';
                    for (int i = 0; i < 4; i++) cab[4 + i] = (byte) (num >> (8 * i));
                    cab[8] = (byte) LARG; cab[9] = (byte) (LARG >> 8); cab[10] = (byte) ALT; cab[11] = (byte) (ALT >> 8);
                    OutputStream o = c.getOutputStream();
                    o.write(cab);
                    o.write(copia);
                    o.flush();
                } catch (Exception e) { }
                try { c.close(); } catch (Exception e) { }
            }
        } catch (Exception e) {
            Log.e(TAG, "quadros pararam", e);
        }
    }

    WebView novoWebView(Context c) {
        WebView w = new WebView(c);
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(false);
        s.setTextZoom(100);
        w.setVerticalScrollBarEnabled(false);
        w.setHorizontalScrollBarEnabled(false);
        w.setWebViewClient(new WebViewClient());
        CookieManager.getInstance().setAcceptThirdPartyCookies(w, true);
        w.loadUrl("about:blank");
        return w;
    }

    /** Tela virtual particular do app: o WebView desenha mesmo com a TV desligada. */
    void telaVirtual() {
        HandlerThread ht = new HandlerThread("leitor");
        ht.start();
        leitor = ImageReader.newInstance(LARG, ALT, PixelFormat.RGBA_8888, 2);
        leitor.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
            public void onImageAvailable(ImageReader r) {   // guarda o último quadro para a porta 9223
                Image im = r.acquireLatestImage();
                if (im == null) return;
                Image.Plane pl = im.getPlanes()[0];
                java.nio.ByteBuffer b = pl.getBuffer();
                int passo = pl.getRowStride();
                synchronized (quadro) {
                    for (int y = 0; y < ALT; y++) {
                        b.position(y * passo);
                        b.get(quadro, y * LARG * 4, LARG * 4);
                    }
                    num_quadro++;
                }
                im.close();
            }
        }, new Handler(ht.getLooper()));
        DisplayManager dm = (DisplayManager) getSystemService(DISPLAY_SERVICE);
        tela = dm.createVirtualDisplay("ps2nav", LARG, ALT, 160, leitor.getSurface(), 0);
        apresentacao = new Presentation(this, tela.getDisplay());
        apresentacao.getWindow().setFlags(WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED);
        web = novoWebView(apresentacao.getContext());
        apresentacao.setContentView(web);
        apresentacao.show();
        Log.i(TAG, "WebView na tela virtual " + LARG + "x" + ALT);
    }

    /** Plano B: janela 640x448 transparente por cima de tudo, sem toque (precisa de SYSTEM_ALERT_WINDOW). */
    void sobreposta() {
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(LARG, ALT,
                android.os.Build.VERSION.SDK_INT >= 26 ? 2038 : WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS, PixelFormat.TRANSLUCENT);
        p.gravity = Gravity.TOP | Gravity.LEFT;
        p.alpha = 0.0f;
        web = novoWebView(this);
        wm.addView(web, p);
        Log.i(TAG, "WebView em janela sobreposta transparente");
    }

    /** 127.0.0.1:9222 ↔ @webview_devtools_remote_<pid> (HTTP /json e WebSocket passam direto). */
    void ponte() {
        try {
            ServerSocket srv = new ServerSocket(PORTA, 8, InetAddress.getByName("127.0.0.1"));
            srv.setReuseAddress(true);
            Log.i(TAG, "ponte DevTools em 127.0.0.1:" + PORTA);
            while (true) {
                final Socket c = srv.accept();
                new Thread(new Runnable() { public void run() { ligar(c); } }).start();
            }
        } catch (Exception e) {
            Log.e(TAG, "ponte parou", e);
        }
    }

    void ligar(Socket c) {
        try {
            LocalSocket l = new LocalSocket();
            l.connect(new LocalSocketAddress("webview_devtools_remote_" + android.os.Process.myPid(),
                    LocalSocketAddress.Namespace.ABSTRACT));
            copiar(c.getInputStream(), l.getOutputStream(), c, l);
            copiar(l.getInputStream(), c.getOutputStream(), c, l);
        } catch (Exception e) {
            Log.w(TAG, "conexão DevTools falhou", e);
            try { c.close(); } catch (Exception x) { }
        }
    }

    static void copiar(final InputStream de, final OutputStream para, final Socket c, final LocalSocket l) {
        new Thread(new Runnable() {
            public void run() {
                byte[] b = new byte[65536];
                try {
                    int n;
                    while ((n = de.read(b)) > 0) { para.write(b, 0, n); para.flush(); }
                } catch (Exception e) { }
                try { c.close(); } catch (Exception e) { }
                try { l.close(); } catch (Exception e) { }
            }
        }).start();
    }
}
