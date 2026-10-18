package br.ps2nav.instalador;

import java.io.IOException;
import java.io.InputStream;

/** Por onde o instalador fala com a TV box: ADB pela rede (do celular) ou a própria box com root (Local). */
public interface Canal {
    String shell(String cmd) throws IOException;

    void enviarArquivo(InputStream dados, String destino, int modo, Adb.Aviso progresso) throws IOException;

    void fechar();
}
