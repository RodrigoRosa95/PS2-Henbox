package br.henbox.conquistas;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;

/**
 * Painel das conquistas do PS2 Henbox: aba "Ao vivo" (página do app xeRAbora na TV box, porta 18280) e aba "Henbox"
 * (página 🏆 do navegador, porta 8780). O endereço da TV box fica nas preferências (⚙). Liga o VigiaService, que
 * notifica cada desbloqueio.
 */
public class MainActivity extends Activity {
    static final String PREFS = "henbox";

    WebView web;
    Button aoVivo, henbox;

    static SharedPreferences prefs(android.content.Context c) {
        return c.getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    /** Ex.: "192.168.0.50" — vazio até a busca automática (ou a pessoa) achar a TV box. */
    static String tvbox(android.content.Context c) {
        return prefs(c).getString("tvbox", BuildConfigHenbox.TVBOX_PADRAO).trim();
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout raiz = new LinearLayout(this);
        raiz.setOrientation(LinearLayout.VERTICAL);
        raiz.setBackgroundColor(Color.rgb(11, 22, 48));

        LinearLayout barra = new LinearLayout(this);
        barra.setGravity(Gravity.CENTER_VERTICAL);
        barra.setPadding(8, 8, 8, 8);
        aoVivo = botao("🎮 Ao vivo");
        henbox = botao("🏆 Henbox");
        Button cfg = botao("⚙");
        barra.addView(aoVivo, new LinearLayout.LayoutParams(0, -2, 1));
        barra.addView(henbox, new LinearLayout.LayoutParams(0, -2, 1));
        barra.addView(cfg, new LinearLayout.LayoutParams(-2, -2));
        raiz.addView(barra);

        web = new WebView(this);
        WebSettings w = web.getSettings();
        w.setJavaScriptEnabled(true);
        w.setDomStorageEnabled(true);
        w.setUseWideViewPort(true);
        w.setLoadWithOverviewMode(true);
        web.setWebViewClient(new WebViewClient());
        raiz.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(raiz);

        aoVivo.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { abrir(true); } });
        henbox.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { abrir(false); } });
        cfg.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { configurar(); } });

        VigiaService.criarCanal(this);   // no Android 13 também traz o pedido de permissão de notificação
        if (Build.VERSION.SDK_INT >= 33)
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        // acha a TV box sozinho: 1º uso, ou o endereço salvo não responde mais (DHCP trocou o IP)
        procurarSeNecessario();
    }

    void procurarSeNecessario() {
        final String ip = tvbox(this);
        final android.app.ProgressDialog pd = android.app.ProgressDialog.show(this, null,
                ip.isEmpty() ? "Procurando a TV box do PS2 Henbox na rede…" : "Conectando à TV box…", true);
        new Thread() {
            public void run() {
                String achado = !ip.isEmpty() && Descobridor.ehHenbox(ip, 2500) ? ip : Descobridor.procurar();
                final String fim = achado;
                runOnUiThread(new Runnable() {
                    public void run() {
                        pd.dismiss();
                        if (fim == null) {
                            android.widget.Toast.makeText(MainActivity.this,
                                    "Não achei a TV box nesta rede. Conecte no Wi-Fi de casa ou digite o endereço.",
                                    android.widget.Toast.LENGTH_LONG).show();
                            if (ip.isEmpty()) configurar(); else abrir(webViewModerno());
                            return;
                        }
                        if (!fim.equals(ip))
                            prefs(MainActivity.this).edit().putString("tvbox", fim).putLong("desde", 0).apply();
                        startService(new Intent(MainActivity.this, VigiaService.class));
                        abrir(webViewModerno());
                    }
                });
            }
        }.start();
    }

    Button botao(String texto) {
        Button bt = new Button(this);
        bt.setText(texto);
        bt.setAllCaps(false);
        return bt;
    }

    /** A página do xeRAbora (aba Ao vivo) precisa de um WebView Chrome 80+; mais velho (Xoom 4.4, TV box com
        WebView 74) começa na aba Henbox, que é HTML simples. */
    boolean webViewModerno() {
        try {
            java.util.regex.Matcher m = java.util.regex.Pattern.compile("Chrome/(\\d+)")
                    .matcher(WebSettings.getDefaultUserAgent(this));
            return m.find() && Integer.parseInt(m.group(1)) >= 80;
        } catch (Exception e) {
            return false;
        }
    }

    void abrir(boolean live) {
        String ip = tvbox(this);
        if (ip.isEmpty()) { configurar(); return; }
        aoVivo.setEnabled(!live);
        henbox.setEnabled(live);
        // a página do xeRAbora precisa do "OPEN TO THE NETWORK" ligado no app dele, na TV box
        web.loadUrl(live ? "http://" + ip + ":18280/#tab=live" : "http://" + ip + ":8780/conquistas");
    }

    void configurar() {
        final EditText campo = new EditText(this);
        campo.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        campo.setHint("ex.: 192.168.0.50");
        campo.setText(tvbox(this));
        final android.widget.CheckBox falar = new android.widget.CheckBox(this);
        falar.setText("Depois do plim, falar \"Você desbloqueou uma conquista no Play 2\"");
        falar.setChecked(prefs(this).getBoolean("falar", true));
        LinearLayout caixa = new LinearLayout(this);
        caixa.setOrientation(LinearLayout.VERTICAL);
        caixa.addView(campo);
        caixa.addView(falar);
        new AlertDialog.Builder(this).setTitle("Endereço da TV box (IP na rede de casa)")
                .setView(caixa)
                .setNeutralButton("🔍 Procurar", new DialogInterface.OnClickListener() {
                    public void onClick(DialogInterface d, int q) {
                        prefs(MainActivity.this).edit().putString("tvbox", "").apply();
                        procurarSeNecessario();
                    }
                })
                .setPositiveButton("Salvar", new DialogInterface.OnClickListener() {
                    public void onClick(DialogInterface d, int q) {
                        String ip = campo.getText().toString().trim().replaceAll("^https?://", "").replaceAll("[:/].*$", "");
                        prefs(MainActivity.this).edit().putString("tvbox", ip).putLong("desde", 0)
                                .putBoolean("falar", falar.isChecked()).apply();
                        startService(new Intent(MainActivity.this, VigiaService.class));
                        abrir(webViewModerno());
                    }
                }).show();
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
