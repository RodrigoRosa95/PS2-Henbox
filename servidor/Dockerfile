# Servidor em nuvem do PS2 Henbox em Docker (23/10/2026): roda em Linux, Windows e Mac (Docker Desktop).
#   docker compose -f servidor/docker-compose.yml up -d      (na raiz do repositório; ver docker-compose.yml)
# Loja/catálogo na porta 8770 (servidor.py) e ROMs/ISOs/loja para a TV box na 8781 (navegador/videos_https.py).
# A chave fica em /dados (volume) e não se perde ao atualizar a imagem.
FROM python:3.12-slim
RUN pip install --no-cache-dir pillow qrcode
WORKDIR /app
COPY . /app
RUN mkdir -p /dados && ln -sf /dados/videos_https.chaves.json /app/navegador/videos_https.chaves.json
ENV PS2_JOGOS=/colecao PS2_CHAVE_ARQ=/dados/videos_https.chave PS2_TVBOX=127.0.0.1 PS2_NAV_IP=127.0.0.1 PYTHONUNBUFFERED=1
EXPOSE 8770 8781
CMD ["sh", "-c", "python3 servidor/parear.py --esperar & (cd /app && python3 servidor.py) & cd /app/navegador && exec python3 videos_https.py"]
