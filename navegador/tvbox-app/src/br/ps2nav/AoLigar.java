package br.ps2nav;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Liga o serviço quando a TV box termina de ligar e pede ao Termux o ~/ps2nav/iniciar.sh (servidores + vigia root):
 *  muitos firmwares de TV box ignoram o Termux:Boot. O iniciar.sh mata o que já estiver rodando antes, então rodar
 *  pelos dois caminhos não duplica nada. Precisa do allow-external-apps do Termux e da permissão RUN_COMMAND
 *  (o instalador dá as duas). */
public class AoLigar extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        c.startService(new Intent(c, Servico.class));
        try {
            Intent t = new Intent("com.termux.RUN_COMMAND");
            t.setClassName("com.termux", "com.termux.app.RunCommandService");
            t.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/home/ps2nav/iniciar.sh");
            t.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
            c.startService(t);
        } catch (Exception e) {
            android.util.Log.w("ps2nav", "Termux não respondeu: " + e);
        }
    }
}
