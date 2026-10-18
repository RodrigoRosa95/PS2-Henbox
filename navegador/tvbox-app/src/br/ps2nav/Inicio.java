package br.ps2nav;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/** Só liga o serviço (o WebView roda numa tela virtual, não aparece na TV) e fecha. */
public class Inicio extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        startService(new Intent(this, Servico.class));
        finish();
    }
}
