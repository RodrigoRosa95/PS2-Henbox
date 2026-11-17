"""Pasta de trabalho do projeto. Troque com a variável PES14_DIR; por padrão é a pasta deste arquivo."""
import os
BASE = os.environ.get('PES14_DIR', os.path.dirname(os.path.abspath(__file__)))
# onde o save publicado fica para a TV box baixar (a pasta é servida por qualquer servidor HTTP em /pes14/)
PUBLICAR = os.environ.get('PES14_PUBLICAR', os.path.join(BASE, 'publicado'))
