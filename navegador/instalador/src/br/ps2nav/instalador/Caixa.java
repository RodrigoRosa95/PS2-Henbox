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

    final Canal adb;
    final AssetManager assets;
    final Adb.Aviso log;
    String uidTermux = "";

    Caixa(Canal adb, AssetManager assets, Adb.Aviso log) {
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
        InputStream i;
        try {
            i = assets.open(nome);
        } catch (IOException e) {
            if (!nome.endsWith(".gz")) throw e;
            i = assets.open(nome.substring(0, nome.length() - 3));   // o aapt descompacta .gz e tira a extensão
        }
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

    /** Instalando na própria box: o Termux e o app do navegador vêm para a frente; o instalador volta à tela. */
    void voltarAoApp() throws IOException {
        if (adb instanceof Local) sh("am start -n br.ps2nav.instalador/.Principal >/dev/null 2>&1");
    }

    void esperar(long ms) { try { Thread.sleep(ms); } catch (InterruptedException e) { } }

    /** Apps (~75 MB, instalados e cópia temporária), pacotes do Termux (~250 MB) e os servidores. */
    static final long ESPACO_MINIMO_MB = 400;

    /** MB livres em /data (onde ficam os apps e o Termux); -1 se não deu para ler. Conferido antes de enviar os APKs,
     *  como o CetusPlay faz (ele avisa "insufficient_storage"). */
    long livreMb() throws IOException {
        String r = su("df -k /data | tail -1");
        String[] c = r.trim().split("\\s+");
        try {
            return Long.parseLong(c[3]) / 1024;
        } catch (Exception e) {
            return -1;
        }
    }

    /** Permissões pelo ADB, sem a pessoa tocar na TV (como o CetusPlay faz com o appops): Termux e o app do navegador
     *  fora da economia de bateria e liberados para rodar em segundo plano. Comandos que o Android da box não tiver
     *  só falham calados. */
    void liberarPermissoes() throws IOException {
        for (String pac : new String[] {"com.termux", "com.termux.boot", "br.ps2nav"}) {
            su("dumpsys deviceidle whitelist +" + pac + " >/dev/null 2>&1; appops set " + pac
                    + " RUN_IN_BACKGROUND allow 2>/dev/null; appops set " + pac + " RUN_ANY_IN_BACKGROUND allow 2>/dev/null");
        }
        su("pm grant com.termux android.permission.POST_NOTIFICATIONS 2>/dev/null; "
                + "pm grant br.ps2nav android.permission.POST_NOTIFICATIONS 2>/dev/null; "
                // o app da box liga o Termux no boot (firmwares que ignoram o Termux:Boot)
                + "pm grant br.ps2nav com.termux.permission.RUN_COMMAND 2>/dev/null");
    }

    void instalar() throws IOException {
        log.aviso("Conferindo root…");
        if (!temRoot()) throw new IOException("a TV box não tem root (su). O instalador precisa de root.");
        String abi = abi();
        log.aviso("Processador: " + abi);
        long livre = livreMb();
        log.aviso("Espaço livre na box: " + livre + " MB");
        if (livre >= 0 && livre < ESPACO_MINIMO_MB)
            throw new IOException("pouco espaço na box (" + livre + " MB livres; precisa de uns " + ESPACO_MINIMO_MB
                    + " MB para os apps, o Python do Termux e os servidores). Apague apps ou arquivos e tente de novo.");
        String termux = abi.contains("arm64") ? "termux-arm64-v8a.apk" : "termux-armeabi-v7a.apk";

        if (!instalado("com.termux")) { log.aviso("Instalando o Termux…"); instalarApk(termux); }
        else log.aviso("Termux já instalado");
        if (!instalado("com.termux.boot")) { log.aviso("Instalando o Termux:Boot…"); instalarApk("termux-boot.apk"); }
        else log.aviso("Termux:Boot já instalado");
        log.aviso("Instalando o PS2 Navegador (WebView da box)…");
        instalarApk("PS2Navegador.apk");

        if (!su("ls " + P + "/bin/bash 2>/dev/null").contains("bash")) {
            log.aviso("Preparando o Termux (1ª vez)…");
            sh("am start -n com.termux/.app.TermuxActivity");
            for (int i = 0; i < 90 && !su("ls " + P + "/bin/bash 2>/dev/null").contains("bash"); i++) esperar(2000);
            if (!su("ls " + P + "/bin/bash 2>/dev/null").contains("bash")) throw new IOException("o Termux não terminou de preparar");
            sh("input keyevent 3");
            voltarAoApp();
        }
        uidTermux = su("stat -c %u " + T);
        log.aviso("Termux pronto (usuário " + uidTermux + ")");
        su("am start -n com.termux.boot/.BootActivity >/dev/null 2>&1; input keyevent 3");   // o Termux:Boot só vale depois de aberto 1 vez
        voltarAoApp();
        su("mkdir -p " + H + "/.termux/boot; grep -q allow-external-apps " + H + "/.termux/termux.properties 2>/dev/null"
                + " || echo allow-external-apps=true >> " + H + "/.termux/termux.properties");

        log.aviso("Copiando os servidores do navegador…");
        enviarAsset("ps2nav.tar.gz", "/data/local/tmp/ps2nav.tar.gz");
        su("rm -rf /data/local/tmp/ps2nav-novo; mkdir -p /data/local/tmp/ps2nav-novo; " + AMB
                + "tar -xf /data/local/tmp/ps2nav.tar.gz -C /data/local/tmp/ps2nav-novo");   // o tar reconhece se é .gz ou não
        // config.json de uma instalação anterior fica (IP do PS2 trocado pelo usuário)
        su("N=/data/local/tmp/ps2nav-novo; mkdir -p " + H + "/ps2nav; "
                + "[ -f " + H + "/ps2nav/config.json ] && rm -f $N/ps2nav/config.json; "
                + "cp -r $N/ps2nav/. " + H + "/ps2nav/; rm -rf " + H + "/udpfs_server; cp -r $N/udpfs_server " + H + "/udpfs_server; "
                + "rm -f " + H + "/.termux/boot/ps2nav " + H + "/.termux/boot/udpfs-ps2.sh; "   // pode ser um link: cp escreveria no alvo
                + "cp $N/boot/ps2nav $N/boot/udpfs-ps2.sh " + H + "/.termux/boot/; chmod 755 " + H + "/.termux/boot/* "
                + H + "/ps2nav/*.sh; chmod 600 " + H + "/ps2nav/config.json; "
                + "chown -R " + uidTermux + ":" + uidTermux + " " + H + "; rm -rf $N /data/local/tmp/ps2nav.tar.gz");

        if (!pythonPronto()) pythonOffline(abi);
        if (!pythonPronto()) {
            log.aviso("Instalando Python e bibliotecas pela internet da box (pode levar vários minutos)…");
            su("rm -f " + H + "/instalar-ps2nav.log");
            rodarNoTermux("instalar-ps2nav.sh", "(yes | pkg update; yes | pkg install python python-pillow; "
                    + "pip install websocket-client) > ~/instalar-ps2nav.log 2>&1; echo FIM >> ~/instalar-ps2nav.log");
            esperarFim("instalar-ps2nav.log", 600);
            if (!pythonPronto()) throw new IOException("Python não ficou pronto (veja ~/instalar-ps2nav.log na box)");
        }
        String ip = ipAutomatico();
        log.aviso("IP do PS2: " + ip);
        if (!ip.startsWith("192.168.4.230 "))
            log.aviso("Este IP não é o padrão: crie no pendrive do PS2 o arquivo APPS/NAVEGADOR/IPCONFIG.DAT com a linha: "
                    + ip);
        log.aviso("Liberando o Termux e o navegador para rodar sempre…");
        liberarPermissoes();
        log.aviso("Ligando os servidores…");
        iniciar();
        esperar(15000);
        log.aviso("Pronto! Copie o navegador.elf para o pendrive do PS2 (botão abaixo, com o navegador aberto) ou pelo PC.");
    }

    boolean pythonPronto() throws IOException {
        return suTermux("python3 -c 'import PIL, websocket; print(1)' 2>/dev/null").equals("1");
    }

    void esperarFim(String logBox, int voltas) throws IOException {
        for (int i = 0; i < voltas; i++) {
            esperar(3000);
            String fim = su("tail -1 " + H + "/" + logBox + " 2>/dev/null");
            if (fim.equals("FIM")) break;
            if (i % 10 == 0 && fim.length() > 0) log.aviso("… " + (fim.length() > 70 ? fim.substring(0, 70) : fim));
        }
    }

    /** Endereço do pacote do Python (os .deb oficiais do Termux + websocket-client), por arquitetura; o celular baixa
     *  e manda para a box, então a box não precisa de internet nem dos espelhos do Termux (o passo que mais falhava). */
    static final String PYTHON_URL = "https://raw.githubusercontent.com/RodrigoRosa95/PS2-Henbox/main/downloads/python-";

    void pythonOffline(String abi) {
        String arq = abi.contains("arm64") ? "aarch64" : abi.contains("x86_64") ? "x86_64" : abi.contains("x86") ? "i686" : "arm";
        String tmp = "/data/local/tmp/python-" + arq + ".tar";
        try {
            log.aviso("Baixando o Python pronto (" + arq + ", ~30 MB)…");
            java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(PYTHON_URL + arq + ".tar").openConnection();
            c.setConnectTimeout(15000);
            c.setReadTimeout(60000);
            if (c.getResponseCode() != 200) throw new IOException("HTTP " + c.getResponseCode());
            InputStream i = c.getInputStream();
            try {
                adb.enviarArquivo(i, tmp, 0644, null);
            } finally {
                i.close();
            }
            log.aviso("Instalando o Python sem internet na box…");
            String d = H + "/python-offline";
            su("rm -rf " + d + "; mkdir -p " + d + "; cd " + d + " && " + AMB + "tar -xf " + tmp + " -C " + d + "; rm -f " + tmp
                    + "; chown -R " + uidTermux + ":" + uidTermux + " " + d + "; rm -f " + H + "/instalar-ps2nav.log");
            rodarNoTermux("instalar-ps2nav.sh", "(cd ~/python-offline && dpkg -i *.deb && pip install --no-index *.whl)"
                    + " > ~/instalar-ps2nav.log 2>&1; rm -rf ~/python-offline; echo FIM >> ~/instalar-ps2nav.log");
            esperarFim("instalar-ps2nav.log", 200);
        } catch (IOException e) {
            log.aviso("Python pronto indisponível (" + e.getMessage() + "); vou pela internet da box");
            try { su("rm -f " + tmp); } catch (IOException ignorado) { }
        }
    }

    /** Para os servidores pelo PID (o pkill -f do Termux não alcança os processos e um padrão na mesma linha mataria
     *  o próprio comando); o udpfs-ps2.sh e o iniciar.sh sobem tudo de novo. */
    void pararServicos() throws IOException {
        su("for p in $(ps -A -o PID,ARGS | grep -E '[s]ervidor_host.py|[n]avegador_servidor.py|[v]ideos.py 8780|[u]dpfs_nuvem.py|[c]entral.py'"
                + " | awk '{print $1}'); do kill $p; done");
    }

    /** O app da box é aberto pelo ADB (o am de dentro do Termux não abre outro app), depois o iniciar.sh no Termux. */
    void iniciar() throws IOException {
        pararServicos();
        sh("am start -n br.ps2nav/.Inicio");
        esperar(4000);
        rodarNoTermux("iniciar-ps2nav.sh", "exec ~/ps2nav/iniciar.sh");
        voltarAoApp();
    }

    /** Se o IP do PS2 não é da rede do cabo da box, escolhe um livre nela (configurar.py ip-auto); "IP MÁSCARA GW". */
    String ipAutomatico() throws IOException {
        if (uidTermux.length() == 0) uidTermux = su("stat -c %u " + T);
        String r = suTermux("python3 ps2nav/configurar.py ip-auto; chown -R " + uidTermux + ":" + uidTermux + " " + H
                + "/ps2nav");
        String[] linhas = r.trim().split("\n");
        return linhas[linhas.length - 1].trim();
    }

    /** Endereço do servidor em nuvem (http://IP:8781 em casa, ou https) e a chave; vazio = sem servidor. */
    void configurarServidor(String url, String chave) throws IOException {
        url = url.trim();
        chave = chave.trim();
        for (String u : url.split("[,\\s]+"))
            if (u.length() > 0 && !u.matches("https?://[A-Za-z0-9.\\-]+(:\\d+)?/?"))
                throw new IOException("endereço inválido: " + u + " (ex.: http://192.168.0.10:8781, https://meu.dominio)");
        if (!chave.matches("[A-Za-z0-9_\\-]*")) throw new IOException("chave inválida");
        if (uidTermux.length() == 0) uidTermux = su("stat -c %u " + T);
        suTermux("python3 ps2nav/configurar.py servidor " + aspas(url) + " " + aspas(chave) + "; chown -R " + uidTermux
                + ":" + uidTermux + " " + H + "/ps2nav");
    }

    String estado() throws IOException { return suTermux("python3 ps2nav/configurar.py estado 2>&1"); }

    /** Lista de conferência (configurar.py checklist): JSON [{ok, item, detalhe, resolver}]. */
    String checklist() throws IOException { return suTermux("python3 ps2nav/configurar.py checklist 2>&1"); }

    // ---- pendrive do PS2 preparado na USB da própria box (preparar-pendrive.sh, root) ----
    /** Uma linha por pendrive na box: "ID|tamanho MB|livre MB|sim/não (tem ISO)|pastas". */
    String[] pendrives() throws IOException {
        String r = su("sh " + H + "/ps2nav/preparar-pendrive.sh listar 2>&1").trim();
        return r.length() == 0 ? new String[0] : r.split("\n");
    }

    // ---- 🎵 música da loja: o usuário envia do celular e cai na pasta MUSICAS do pendrive da box (24/10/2026) ----
    /** Formatos que a videos.py da box sabe converter para o som do PS2 (MUSICAS_EXT de videos.py). */
    static final String[] MUSICAS_EXT = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus"};

    boolean musicaConhecida(String nome) {
        String b = nome.toLowerCase();
        for (String e : MUSICAS_EXT) if (b.endsWith(e)) return true;
        return false;
    }

    /** Pasta MUSICAS do pendrive em /storage da box (a que a videos.py procura); cria se ainda não existe. */
    String pastaMusicas() throws IOException {
        String p = sh("ls -d /storage/*-*/MUSICAS 2>/dev/null | head -1").trim();
        if (p.isEmpty()) {
            String raiz = sh("ls -d /storage/* 2>/dev/null | grep -vw /storage/self | head -1").trim();
            if (raiz.isEmpty()) throw new IOException("nenhum pendrive na USB da TV box. Espete um com a pasta MUSICAS e tente de novo.");
            p = raiz + "/MUSICAS";
            String r = su("mkdir -p " + aspas(p) + " && echo ok");
            if (!r.trim().endsWith("ok")) throw new IOException("não criei a pasta MUSICAS: " + r.trim());
        }
        return p;
    }

    /** Envio completo: o arquivo vai por ADB para /data/local/tmp e um cp como root o põe no pendrive
     *  (o Termux da box não escreve no FAT32, o root sim). Devolve o caminho no pendrive. */
    String enviarMusica(String nome, InputStream dados) throws IOException {
        final String limpo = nomeLimpo(nome);
        String pasta = pastaMusicas();
        String cheio = pasta + "/" + limpo;
        String tmp = "/data/local/tmp/henbox-musica" + Long.toString(System.currentTimeMillis(), 36);
        try {
            adb.enviarArquivo(dados, tmp, 0644, null);
            String r = su("cp " + aspas(tmp) + " " + aspas(cheio) + " && chmod 660 " + aspas(cheio)
                    + " && echo copiei-ok; rm -f " + aspas(tmp));
            if (!r.trim().endsWith("copiei-ok"))
                throw new IOException("não copiei para o pendrive da TV box: " + resumo(r));
        } finally {
            su("rm -f " + aspas(tmp) + " 2>/dev/null");
        }
        return cheio;
    }

    String nomeLimpo(String nome) throws IOException {
        if (nome == null || nome.trim().isEmpty()) throw new IOException("nome vazio");
        String b = nome.replace('\\', '/');
        b = b.substring(b.lastIndexOf('/') + 1);
        b = b.replaceAll("[\\x00-\\x1f\\x7f/:*?\"<>|]", "_").trim();
        if (!musicaConhecida(b))
            throw new IOException("formato não suportado (" + nome + "): use "
                    + android.text.TextUtils.join(", ", MUSICAS_EXT));
        return b;
    }

    String resumo(String r) {
        String s = r.replace('\n', ' ').trim();
        return s.length() > 200 ? s.substring(s.length() - 200) : s;
    }

    String prepararPendrive(String id, boolean formatar) throws IOException {
        if (!id.matches("[A-Za-z0-9-]+")) throw new IOException("pendrive inválido");
        if (uidTermux.length() == 0) uidTermux = su("stat -c %u " + T);
        suTermux("python3 ps2nav/configurar.py aplicar >/dev/null 2>&1; chown -R " + uidTermux + ":" + uidTermux + " "
                + H + "/ps2nav");   // IPCONFIG.DAT em dia
        return su("sh " + H + "/ps2nav/preparar-pendrive.sh preparar " + id + (formatar ? " formatar" : "") + " 2>&1");
    }

    // ---- 🏆 conquistas: xeRAbora oficial (sem licença de redistribuição: o celular baixa do GitHub do autor) ----
    static final String XERA = "io.github.hacan359.xerabora";

    void instalarXerabora() throws IOException {
        log.aviso("Procurando a versão mais nova do xeRAbora (github.com/hacan359/xerabora)…");
        org.json.JSONArray rel;
        try {
            rel = new org.json.JSONArray(new String(baixar("https://api.github.com/repos/hacan359/xerabora/releases?per_page=5"), "UTF-8"));
        } catch (org.json.JSONException e) {
            throw new IOException("resposta estranha do GitHub");
        }
        String apk = null, somas = null, versao = "";
        for (int k = 0; k < rel.length() && apk == null; k++) {
            org.json.JSONObject r = rel.optJSONObject(k);
            org.json.JSONArray as = r.optJSONArray("assets");
            for (int j = 0; as != null && j < as.length(); j++) {
                org.json.JSONObject a = as.optJSONObject(j);
                if (a.optString("name").equals("xerabora-android.apk")) apk = a.optString("browser_download_url");
                if (a.optString("name").equals("SHA256SUMS")) somas = a.optString("browser_download_url");
            }
            versao = r.optString("tag_name");
            if (apk == null) somas = null;
        }
        if (apk == null) throw new IOException("o xeRAbora não tem APK de Android publicado agora");
        log.aviso("Baixando o xeRAbora " + versao + "…");
        byte[] dados = baixar(apk);
        if (somas != null) {
            String lista = new String(baixar(somas), "UTF-8");
            String sha = sha256(dados);
            if (!lista.contains(sha)) throw new IOException("o APK baixado não confere com o SHA256SUMS");
        }
        String tmp = "/data/local/tmp/xerabora.apk";
        adb.enviarArquivo(new ByteArrayInputStream(dados), tmp, 0644, null);
        String r = sh("pm install -r " + tmp);
        sh("rm -f " + tmp);
        if (!r.contains("Success")) throw new IOException("não instalou o xeRAbora: " + r);
        su("dumpsys deviceidle whitelist +" + XERA + " >/dev/null 2>&1; appops set " + XERA + " RUN_IN_BACKGROUND allow 2>/dev/null");
        sh("monkey -p " + XERA + " -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1");
        log.aviso("xeRAbora instalado e aberto na TV. Na TV: entre com o SEU usuário do RetroAchievements e ligue "
                + "\"OPEN TO THE NETWORK\". Depois disso a box mantém o motor ligado sozinha.");
    }

    static byte[] baixar(String url) throws IOException {
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(60000);
        c.setRequestProperty("User-Agent", "ps2-henbox");
        if (c.getResponseCode() != 200) throw new IOException("HTTP " + c.getResponseCode() + " em " + url);
        InputStream i = c.getInputStream();
        java.io.ByteArrayOutputStream b = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[65536];
        for (int n; (n = i.read(buf)) > 0; ) b.write(buf, 0, n);
        i.close();
        return b.toByteArray();
    }

    static String sha256(byte[] d) throws IOException {
        try {
            byte[] h = java.security.MessageDigest.getInstance("SHA-256").digest(d);
            StringBuilder sb = new StringBuilder();
            for (byte x : h) sb.append(String.format("%02x", x & 0xff));
            return sb.toString();
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException(e.toString());
        }
    }

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
