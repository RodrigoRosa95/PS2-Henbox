package br.ps2nav.instalador;

import android.content.res.AssetManager;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Tudo o que o instalador faz na TV box pelo ADB (o mesmo roteiro da instalação feita à mão em 17/10/2026):
 *  - comandos como root (su -c), porque o Termux e os apps são de outros usuários;
 *  - comandos DENTRO do Termux pelo RUN_COMMAND (allow-external-apps=true): o su desta box não passa o grupo de
 *    internet para outro usuário e o apt do Termux se recusa a rodar como root;
 *  - Python como root com o ambiente do Termux só para ler o estado (configurar.py).
 */
public class Caixa {
    static final String T = "/data/data/com.termux";
    static final String P = T + "/files/usr", H = T + "/files/home";
    static final String AMB = "export PREFIX=" + P + " HOME=" + H + " PATH=" + P + "/bin:/system/bin LD_LIBRARY_PATH="
            + P + "/lib TMPDIR=" + P + "/tmp LANG=pt_BR.UTF-8; cd " + H + "; ";

    final Adb adb;
    final AssetManager assets;
    final Adb.Aviso log;
    String uidTermux = "";

    Caixa(Adb adb, AssetManager assets, Adb.Aviso log) {
        this.adb = adb;
        this.assets = assets;
        this.log = log;
    }

    static String aspas(String s) { return "'" + s.replace("'", "'\\''") + "'"; }

    String sh(String cmd) throws IOException { return adb.shell(cmd).trim(); }

    String su(String cmd) throws IOException { return sh("su -c " + aspas(cmd)); }

    /** Python/ferramentas do Termux rodando como root (só leitura de estado e tarefas sem internet). */
    String suTermux(String cmd) throws IOException { return su(AMB + cmd); }

    boolean temRoot() throws IOException { return su("id").contains("uid=0"); }

    String abi() throws IOException { return sh("getprop ro.product.cpu.abi"); }

    boolean instalado(String pacote) throws IOException { return sh("pm path " + pacote).startsWith("package:"); }

    void enviarAsset(String nome, String destino) throws IOException {
        InputStream i = assets.open(nome);
        try {
            adb.enviarArquivo(i, destino, 0644, null);
        } finally {
            i.close();
        }
    }

    void enviarTexto(String texto, String destino) throws IOException {
        adb.enviarArquivo(new ByteArrayInputStream(texto.getBytes("UTF-8")), destino, 0755, null);
    }

    void instalarApk(String asset) throws IOException {
        String tmp = "/data/local/tmp/" + asset;
        enviarAsset(asset, tmp);
        String r = sh("pm install -r " + tmp);
        sh("rm -f " + tmp);
        if (!r.contains("Success")) throw new IOException("não instalou " + asset + ": " + r);
    }

    /** Roda um script dentro do app Termux (com internet). O script vira um arquivo no home do Termux. */
    void rodarNoTermux(String nome, String script) throws IOException {
        String tmp = "/data/local/tmp/" + nome;
        enviarTexto("#!" + P + "/bin/bash\n" + script + "\n", tmp);
        su("cp " + tmp + " " + H + "/" + nome + "; chmod 755 " + H + "/" + nome + "; chown " + uidTermux + ":" + uidTermux
                + " " + H + "/" + nome + "; rm -f " + tmp);
        su("am startservice --user 0 -n com.termux/com.termux.app.RunCommandService -a com.termux.RUN_COMMAND"
                + " --es com.termux.RUN_COMMAND_PATH " + H + "/" + nome + " --ez com.termux.RUN_COMMAND_BACKGROUND true");
    }

    void esperar(long ms) { try { Thread.sleep(ms); } catch (InterruptedException e) { } }

    void instalar() throws IOException {
        log.aviso("Conferindo root…");
        if (!temRoot()) throw new IOException("a TV box não tem root (su). O instalador precisa de root.");
        String abi = abi();
        log.aviso("Processador: " + abi);
        String termux = abi.contains("arm64") ? "termux-arm64-v8a.apk" : "termux-armeabi-v7a.apk";

        if (!instalado("com.termux")) { log.aviso("Instalando o Termux…"); instalarApk(termux); }
        else log.aviso("Termux já instalado");
        if (!instalado("com.termux.boot")) { log.aviso("Instalando o Termux:Boot…"); instalarApk("termux-boot.apk"); }
        else log.aviso("Termux:Boot já instalado");
        log.aviso("Instalando o PS2 Navegador (WebView da box)…");
        instalarApk("PS2Navegador.apk");

        if (!su("ls " + P + "/bin/bash 2>/dev/null").contains("bash")) {
            log.aviso("Preparando o Termux (1ª vez, precisa de internet na box)…");
            sh("am start -n com.termux/.app.TermuxActivity");
            for (int i = 0; i < 90 && !su("ls " + P + "/bin/bash 2>/dev/null").contains("bash"); i++) esperar(2000);
            if (!su("ls " + P + "/bin/bash 2>/dev/null").contains("bash")) throw new IOException("o Termux não terminou de preparar");
            sh("input keyevent 3");
        }
        uidTermux = su("stat -c %u " + T);
        log.aviso("Termux pronto (usuário " + uidTermux + ")");
        su("am start -n com.termux.boot/.BootActivity >/dev/null 2>&1; input keyevent 3");   // o Termux:Boot só vale depois de aberto 1 vez
        su("mkdir -p " + H + "/.termux/boot; grep -q allow-external-apps " + H + "/.termux/termux.properties 2>/dev/null"
                + " || echo allow-external-apps=true >> " + H + "/.termux/termux.properties");

        log.aviso("Copiando os servidores do navegador…");
        enviarAsset("ps2nav.tar.gz", "/data/local/tmp/ps2nav.tar.gz");
        su("rm -rf /data/local/tmp/ps2nav-novo; mkdir -p /data/local/tmp/ps2nav-novo; " + AMB
                + "tar -xzf /data/local/tmp/ps2nav.tar.gz -C /data/local/tmp/ps2nav-novo");
        // config.json de uma instalação anterior fica (IP do PS2 trocado pelo usuário)
        su("N=/data/local/tmp/ps2nav-novo; mkdir -p " + H + "/ps2nav; "
                + "[ -f " + H + "/ps2nav/config.json ] && rm -f $N/ps2nav/config.json; "
                + "cp -r $N/ps2nav/. " + H + "/ps2nav/; rm -rf " + H + "/udpfs_server; cp -r $N/udpfs_server " + H + "/udpfs_server; "
                + "rm -f " + H + "/.termux/boot/ps2nav " + H + "/.termux/boot/udpfs-ps2.sh; "   // pode ser um link: cp escreveria no alvo
                + "cp $N/boot/ps2nav $N/boot/udpfs-ps2.sh " + H + "/.termux/boot/; chmod 755 " + H + "/.termux/boot/* "
                + H + "/ps2nav/*.sh; chmod 600 " + H + "/ps2nav/config.json; "
                + "chown -R " + uidTermux + ":" + uidTermux + " " + H + "; rm -rf $N /data/local/tmp/ps2nav.tar.gz");

        if (!suTermux("python3 -c 'import PIL, websocket; print(1)' 2>/dev/null").equals("1")) {
            log.aviso("Instalando Python e bibliotecas no Termux (pode levar vários minutos)…");
            su("rm -f " + H + "/instalar-ps2nav.log");
            rodarNoTermux("instalar-ps2nav.sh", "(yes | pkg update; yes | pkg install python python-pillow; "
                    + "pip install websocket-client) > ~/instalar-ps2nav.log 2>&1; echo FIM >> ~/instalar-ps2nav.log");
            for (int i = 0; i < 600; i++) {
                esperar(3000);
                String fim = su("tail -1 " + H + "/instalar-ps2nav.log 2>/dev/null");
                if (fim.equals("FIM")) break;
                if (i % 10 == 0 && fim.length() > 0) log.aviso("… " + (fim.length() > 70 ? fim.substring(0, 70) : fim));
            }
            if (!suTermux("python3 -c 'import PIL, websocket; print(1)' 2>/dev/null").equals("1"))
                throw new IOException("Python não ficou pronto (veja ~/instalar-ps2nav.log na box)");
        }
        log.aviso("Ligando os servidores…");
        iniciar();
        esperar(15000);
        log.aviso("Pronto! Copie o navegador.elf para o pendrive do PS2 (botão abaixo, com o navegador aberto) ou pelo PC.");
    }

    /** Para os servidores pelo PID (o pkill -f do Termux não alcança os processos e um padrão na mesma linha mataria
     *  o próprio comando); o udpfs-ps2.sh e o iniciar.sh sobem tudo de novo. */
    void pararServicos() throws IOException {
        su("for p in $(ps -A -o PID,ARGS | grep -E '[s]ervidor_host.py|[n]avegador_servidor.py|[v]ideos.py 8780|[u]dpfs_nuvem.py'"
                + " | awk '{print $1}'); do kill $p; done");
    }

    /** O app da box é aberto pelo ADB (o am de dentro do Termux não abre outro app), depois o iniciar.sh no Termux. */
    void iniciar() throws IOException {
        pararServicos();
        sh("am start -n br.ps2nav/.Inicio");
        esperar(4000);
        rodarNoTermux("iniciar-ps2nav.sh", "exec ~/ps2nav/iniciar.sh");
    }

    String estado() throws IOException { return suTermux("python3 ps2nav/configurar.py estado 2>&1"); }

    void trocarIp(String ip, String mascara, String gw) throws IOException {
        if (!ip.matches("\\d+\\.\\d+\\.\\d+\\.\\d+") || !mascara.matches("\\d+\\.\\d+\\.\\d+\\.\\d+")
                || !gw.matches("\\d+\\.\\d+\\.\\d+\\.\\d+")) throw new IOException("IP inválido");
        uidTermux = su("stat -c %u " + T);
        suTermux("python3 ps2nav/configurar.py ip " + ip + " " + mascara + " " + gw + "; chown -R " + uidTermux + ":"
                + uidTermux + " " + H + "/ps2nav");
    }

    /** Pede ao navegador aberto no PS2 para gravar um arquivo da box no pendrive (porta 8772, "copiar2"). */
    String gravarNoPendrive(String origem, String destino) throws IOException {
        return sh("echo " + aspas("copiar2 host:" + origem + "|mass:/APPS/NAVEGADOR/" + destino + "|app:" + destino)
                + " | toybox nc -w 5 127.0.0.1 8772");
    }
}
