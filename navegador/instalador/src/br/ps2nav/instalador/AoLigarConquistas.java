package br.ps2nav.instalador;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Celular ligado (ou app atualizado): volta a vigiar as conquistas sem precisar abrir o app. */
public class AoLigarConquistas extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        if (!Conquistas.tvbox(c).isEmpty())
            c.startService(new Intent(c, VigiaConquistas.class));
    }
}
