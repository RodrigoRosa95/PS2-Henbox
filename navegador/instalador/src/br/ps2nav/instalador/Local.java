package br.ps2nav.instalador;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * O instalador rodando NA PRÓPRIA TV box (pedido do usuário 18/10/2026): em vez do ADB, cada comando roda como root
 * (su -c), que é o que o shell do ADB fazia com os comandos de pm/am. Arquivos passam pela pasta do app e o root copia.
 */
public class Local implements Canal {
    final File tmp;

    public Local(File pastaCache) { tmp = pastaCache; }

    public String shell(String cmd) throws IOException {
        Process p = new ProcessBuilder("su", "-c", cmd).redirectErrorStream(true).start();
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        InputStream i = p.getInputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = i.read(buf)) > 0) b.write(buf, 0, n);
        try { p.waitFor(); } catch (InterruptedException e) { }
        return b.toString("UTF-8");
    }

    public void enviarArquivo(InputStream dados, String destino, int modo, Adb.Aviso progresso) throws IOException {
        File f = new File(tmp, "envio.tmp");
        FileOutputStream o = new FileOutputStream(f);
        try {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = dados.read(buf)) > 0) o.write(buf, 0, n);
        } finally {
            o.close();
        }
        f.setReadable(true, false);
        String r = shell("cp " + Caixa.aspas(f.getAbsolutePath()) + " " + Caixa.aspas(destino) + " && chmod "
                + Integer.toOctalString(modo) + " " + Caixa.aspas(destino) + " && echo ok");
        f.delete();
        if (!r.trim().endsWith("ok")) throw new IOException("não copiou para " + destino + ": " + r.trim());
    }

    public void fechar() { }
}
