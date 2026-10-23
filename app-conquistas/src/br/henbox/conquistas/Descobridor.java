package br.henbox.conquistas;

import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Acha a TV box do PS2 Henbox sozinho: pega o IPv4 do próprio celular na rede local (Wi-Fi) e pergunta
 * http://<vizinho>:8780/henbox a todos os endereços da mesma /24, 48 de cada vez; a box responde {"app": "ps2-henbox"}.
 * Leva poucos segundos. Só procura na rede local (nunca fora dela).
 */
final class Descobridor {
    private Descobridor() {
    }

    /** Prefixo "192.168.4." da rede local do celular, ou null sem Wi-Fi/rede local. */
    static String prefixo() {
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address && a.isSiteLocalAddress()) {
                        String ip = a.getHostAddress();
                        return ip.substring(0, ip.lastIndexOf('.') + 1);
                    }
                }
            }
        } catch (Exception ignorado) {
        }
        return null;
    }

    static boolean ehHenbox(String ip, int espera) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL("http://" + ip + ":8780/henbox").openConnection();
            c.setConnectTimeout(espera);
            c.setReadTimeout(espera);
            if (c.getResponseCode() != 200) return false;
            byte[] b = new byte[256];
            int n = c.getInputStream().read(b);
            return n > 0 && new String(b, 0, n, "UTF-8").contains("ps2-henbox");
        } catch (Exception e) {
            return false;
        }
    }

    /** IP da TV box ou null. Bloqueia (rodar fora da tela). */
    static String procurar() {
        final String pre = prefixo();
        if (pre == null) return null;
        final AtomicReference<String> achado = new AtomicReference<String>();
        ExecutorService pool = Executors.newFixedThreadPool(48);
        for (int i = 1; i < 255; i++) {
            final String ip = pre + i;
            pool.execute(new Runnable() {
                public void run() {
                    if (achado.get() == null && ehHenbox(ip, 700)) achado.compareAndSet(null, ip);
                }
            });
        }
        pool.shutdown();
        try {
            pool.awaitTermination(20, TimeUnit.SECONDS);
        } catch (InterruptedException ignorado) {
        }
        pool.shutdownNow();
        return achado.get();
    }
}
