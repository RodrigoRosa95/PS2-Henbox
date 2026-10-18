package br.ps2nav;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Liga o serviço quando a TV box termina de ligar. */
public class AoLigar extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        c.startService(new Intent(c, Servico.class));
    }
}
