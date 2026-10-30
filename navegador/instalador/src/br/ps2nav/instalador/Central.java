package br.ps2nav.instalador;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

import org.json.JSONObject;

/**
 * Central do celular (pedido do usuário 24/10/2026): a página /celular do central.py da TV box (porta 8785) num
 * WebView — capas, arquivos do PS2 e do pendrive da box, controle remoto, kits online — mais a ponte window.Henbox,
 * que liga o ServidorIsos e devolve o endereço e a chave para a página registrar os ISOs deste celular na box.
 * Extra "box": IP da TV box (do Principal); sem ele, procura na rede (Descobridor).
 */
public class Central extends Activity {
    WebView web;
    String box;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        ServidorIsos.carregarChave(this);
        final TextView espera = new TextView(this);
        espera.setPadding(40, 40, 40, 40);
        espera.setTextSize(18);
        espera.setText("Procurando a TV box na rede…");
        setContentView(espera);
        if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission("android.permission.READ_EXTERNAL_STORAGE")
                != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{"android.permission.READ_EXTERNAL_STORAGE"}, 1);
        box = getIntent().getStringExtra("box");
        new Thread(new Runnable() {
            public void run() {
                if (box != null && box.length() > 0 && !responde(box)) box = null;   // IP guardado de outro dia
                if (box == null || box.length() == 0) box = Descobridor.procurar();
                runOnUiThread(new Runnable() {
                    public void run() {
                        if (box == null) espera.setText("Não achei a TV box. Celular e box precisam estar no mesmo Wi-Fi, "
                                + "com os serviços do PS2 Henbox ligados na box.");
                        else abrir();
                    }
                });
            }
        }).start();
    }

    static boolean responde(String ip) {
        try {
            java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL("http://" + ip + ":8785/henbox").openConnection();
            c.setConnectTimeout(1500);
            c.setReadTimeout(1500);
            return c.getResponseCode() == 200;
        } catch (Exception e) {
            return false;
        }
    }

    void abrir() {
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient());   // confirm()/prompt() da página
        web.addJavascriptInterface(new Ponte(), "Henbox");
        setContentView(web);
        web.loadUrl("http://" + box + ":8785/celular");
    }

    /** window.Henbox na página. */
    class Ponte {
        /** Baixa um arquivo do PS2/box para a pasta Download do celular (o WebView não baixa sozinho). */
        @JavascriptInterface
        public void baixar(String url, String nome) {
            android.app.DownloadManager dm = (android.app.DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            dm.enqueue(new android.app.DownloadManager.Request(android.net.Uri.parse(url)).setTitle(nome)
                    .setNotificationVisibility(android.app.DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    .setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS, nome));
        }

        /** Liga o servidor de ISOs, procura os ISOs e devolve {"url", "chave"} (ou {"erro"}). Bloqueia a thread do JS. */
        @JavascriptInterface
        public String servidor() {
            try {
                if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission("android.permission.READ_EXTERNAL_STORAGE")
                        != PackageManager.PERMISSION_GRANTED) {
                    runOnUiThread(new Runnable() { public void run() {
                        requestPermissions(new String[]{"android.permission.READ_EXTERNAL_STORAGE"}, 1); } });
                    return new JSONObject().put("erro", "Permita o acesso aos arquivos e toque de novo em Procurar.").toString();
                }
                startService(new Intent(Central.this, ServidorIsos.class));
                ServidorIsos.procurar();
                for (int i = 0; i < 30 && !ServidorIsos.ligado; i++) Thread.sleep(100);
                String ip = ServidorIsos.meuIp(box);
                if (ip == null) return new JSONObject().put("erro", "celular sem rede local (Wi-Fi)").toString();
                return new JSONObject().put("url", "http://" + ip + ":" + ServidorIsos.PORTA)
                        .put("chave", ServidorIsos.chave()).put("isos", ServidorIsos.isos.size()).toString();
            } catch (Exception e) {
                return "{\"erro\":\"" + String.valueOf(e.getMessage()).replace("\"", "'") + "\"}";
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
