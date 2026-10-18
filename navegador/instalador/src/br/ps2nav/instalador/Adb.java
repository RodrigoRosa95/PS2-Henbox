package br.ps2nav.instalador;

import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.math.BigInteger;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

/**
 * Cliente ADB por TCP (porta 5555), sem PC: conexão, autenticação RSA (a TV pergunta "Permitir depuração?" na 1ª vez),
 * comandos shell: e envio de arquivos por sync:. Um canal por vez, que é o que o instalador precisa.
 * Protocolo: https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/protocol.txt
 */
public class Adb {
    static final int CNXN = 0x4e584e43, AUTH = 0x48545541, OPEN = 0x4e45504f, OKAY = 0x59414b4f,
            CLSE = 0x45534c43, WRTE = 0x45545257;
    static final int VERSAO = 0x01000001, MAXDATA = 256 * 1024;
    /** DigestInfo do SHA-1: o adbd confere a assinatura do token (20 bytes) como um hash SHA-1. */
    static final byte[] PREFIXO_SHA1 = {0x30, 0x21, 0x30, 0x09, 0x06, 0x05, 0x2b, 0x0e, 0x03, 0x02, 0x1a, 0x05, 0x00,
            0x04, 0x14};

    public interface Aviso { void aviso(String s); }

    Socket s;
    DataInputStream in;
    OutputStream out;
    KeyPair chave;
    int proximo_id = 1;
    int maxDados = 4096;   /* o que a box aceita por pacote (vem no CNXN dela; caixas antigas: 4 KB) */

    /** Chave RSA do app (criada uma vez e guardada): a TV lembra dela depois de "Sempre permitir". */
    public static KeyPair chave(File pasta) throws Exception {
        File priv = new File(pasta, "adbkey"), pub = new File(pasta, "adbkey.pub.der");
        KeyFactory kf = KeyFactory.getInstance("RSA");
        if (priv.exists() && pub.exists()) {
            return new KeyPair(kf.generatePublic(new X509EncodedKeySpec(ler(pub))),
                    kf.generatePrivate(new PKCS8EncodedKeySpec(ler(priv))));
        }
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        KeyPair kp = g.generateKeyPair();
        gravar(priv, kp.getPrivate().getEncoded());
        gravar(pub, kp.getPublic().getEncoded());
        return kp;
    }

    public Adb(String host, KeyPair chave, Aviso aviso) throws Exception {
        this.chave = chave;
        s = new Socket();
        s.connect(new InetSocketAddress(host, 5555), 5000);
        s.setSoTimeout(120000);   // tempo para a pessoa autorizar na TV
        in = new DataInputStream(s.getInputStream());
        out = s.getOutputStream();
        enviar(CNXN, VERSAO, MAXDATA, "host::PS2 Navegador\0".getBytes("UTF-8"));
        boolean mandou_assinatura = false;
        while (true) {
            Msg m = receber();
            if (m.cmd == CNXN) { maxDados = Math.max(1024, Math.min(MAXDATA, m.arg1)); break; }
            if (m.cmd != AUTH || m.arg0 != 1) throw new IOException("resposta inesperada do ADB");
            if (!mandou_assinatura) {
                enviar(AUTH, 2, 0, assinar(m.dados));
                mandou_assinatura = true;
            } else {
                if (aviso != null) aviso.aviso("Na TV: aceite \"Permitir depuração\" (marque \"Sempre permitir\")");
                enviar(AUTH, 3, 0, chavePublicaAndroid());
            }
        }
        s.setSoTimeout(60000);
    }

    public void fechar() {
        try { s.close(); } catch (Exception e) { }
    }

    /** Roda um comando na TV box e devolve a saída. */
    public String shell(String cmd) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int local = proximo_id++;
        enviar(OPEN, local, 0, ("shell:" + cmd + "\0").getBytes("UTF-8"));
        int remoto = 0;
        while (true) {
            Msg m = receber();
            if (m.arg1 != local) continue;
            if (m.cmd == OKAY) { remoto = m.arg0; continue; }
            if (m.cmd == WRTE) { b.write(m.dados); enviar(OKAY, local, m.arg0, null); continue; }
            if (m.cmd == CLSE) { enviar(CLSE, local, m.arg0, null); break; }
        }
        return b.toString("UTF-8");
    }

    /** Envia um arquivo (sync: SEND/DATA/DONE). */
    public void enviarArquivo(InputStream dados, String destino, int modo, Aviso progresso) throws IOException {
        int local = proximo_id++;
        enviar(OPEN, local, 0, "sync:\0".getBytes("UTF-8"));
        int remoto = esperarOkay(local);
        byte[] caminho = (destino + "," + modo).getBytes("UTF-8");
        ByteArrayOutputStream pac = new ByteArrayOutputStream();
        pac.write(sync("SEND", caminho.length));
        pac.write(caminho);
        escreverCanal(local, remoto, pac.toByteArray());
        byte[] buf = new byte[60 * 1024];
        long total = 0;
        int n;
        while ((n = dados.read(buf)) > 0) {
            pac.reset();
            pac.write(sync("DATA", n));
            pac.write(buf, 0, n);
            escreverCanal(local, remoto, pac.toByteArray());
            total += n;
            if (progresso != null && (total % (2 << 20)) < n) progresso.aviso((total >> 20) + " MB");
        }
        escreverCanal(local, remoto, sync("DONE", (int) (System.currentTimeMillis() / 1000)));
        // resposta: OKAY ou FAIL (sync), depois QUIT
        while (true) {
            Msg m = receber();
            if (m.arg1 != local) continue;
            if (m.cmd == WRTE) {
                enviar(OKAY, local, m.arg0, null);
                String id = new String(m.dados, 0, 4, "US-ASCII");
                if (id.equals("FAIL")) throw new IOException("falhou: " + new String(m.dados, 8, m.dados.length - 8, "UTF-8"));
                if (id.equals("OKAY")) break;
            }
            if (m.cmd == CLSE) throw new IOException("canal fechado no envio");
        }
        escreverCanal(local, remoto, sync("QUIT", 0));
        enviar(CLSE, local, remoto, null);
    }

    void escreverCanal(int local, int remoto, byte[] d) throws IOException {
        for (int i = 0; i < d.length; i += maxDados) {
            int n = Math.min(maxDados, d.length - i);
            byte[] p = new byte[n];
            System.arraycopy(d, i, p, 0, n);
            enviar(WRTE, local, remoto, p);
            esperarOkay(local);
        }
    }

    int esperarOkay(int local) throws IOException {
        while (true) {
            Msg m = receber();
            if (m.arg1 != local) continue;
            if (m.cmd == OKAY) return m.arg0;
            if (m.cmd == CLSE) throw new IOException("a TV box fechou o canal");
        }
    }

    static byte[] sync(String id, int n) throws IOException {
        ByteBuffer b = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN);
        b.put(id.getBytes("US-ASCII")).putInt(n);
        return b.array();
    }

    static class Msg { int cmd, arg0, arg1; byte[] dados; }

    void enviar(int cmd, int a0, int a1, byte[] dados) throws IOException {
        int n = dados == null ? 0 : dados.length, soma = 0;
        for (int i = 0; i < n; i++) soma += dados[i] & 0xff;
        ByteBuffer b = ByteBuffer.allocate(24).order(ByteOrder.LITTLE_ENDIAN);
        b.putInt(cmd).putInt(a0).putInt(a1).putInt(n).putInt(soma).putInt(cmd ^ 0xffffffff);
        synchronized (this) {
            out.write(b.array());
            if (n > 0) out.write(dados);
            out.flush();
        }
    }

    Msg receber() throws IOException {
        byte[] cab = new byte[24];
        in.readFully(cab);
        ByteBuffer b = ByteBuffer.wrap(cab).order(ByteOrder.LITTLE_ENDIAN);
        Msg m = new Msg();
        m.cmd = b.getInt(); m.arg0 = b.getInt(); m.arg1 = b.getInt();
        int n = b.getInt();
        m.dados = new byte[n];
        in.readFully(m.dados);
        return m;
    }

    byte[] assinar(byte[] token) throws Exception {
        Signature sg = Signature.getInstance("NONEwithRSA");
        sg.initSign((PrivateKey) chave.getPrivate());
        sg.update(PREFIXO_SHA1);
        sg.update(token);
        return sg.sign();
    }

    /** Chave pública no formato do adbd (RSAPublicKey do mincrypt, little-endian) em base64 + nome. */
    byte[] chavePublicaAndroid() throws IOException {
        RSAPublicKey pub = (RSAPublicKey) chave.getPublic();
        BigInteger n = pub.getModulus(), r32 = BigInteger.ONE.shiftLeft(32);
        int palavras = 2048 / 32;
        BigInteger n0inv = n.mod(r32).modInverse(r32).negate().mod(r32);
        BigInteger rr = BigInteger.ONE.shiftLeft(2048).modPow(BigInteger.valueOf(2), n);
        ByteBuffer b = ByteBuffer.allocate(4 + 4 + palavras * 4 * 2 + 4).order(ByteOrder.LITTLE_ENDIAN);
        b.putInt(palavras).putInt(n0inv.intValue());
        for (int i = 0; i < palavras; i++) b.putInt(n.shiftRight(32 * i).mod(r32).intValue());
        for (int i = 0; i < palavras; i++) b.putInt(rr.shiftRight(32 * i).mod(r32).intValue());
        b.putInt(pub.getPublicExponent().intValue());
        String txt = Base64.encodeToString(b.array(), Base64.NO_WRAP) + " ps2navegador@celular\0";
        return txt.getBytes("UTF-8");
    }

    static byte[] ler(File f) throws IOException {
        FileInputStream i = new FileInputStream(f);
        byte[] d = new byte[(int) f.length()];
        new DataInputStream(i).readFully(d);
        i.close();
        return d;
    }

    static void gravar(File f, byte[] d) throws IOException {
        FileOutputStream o = new FileOutputStream(f);
        o.write(d);
        o.close();
    }
}
