#!/usr/bin/env python3
"""
Gerar Arte Completa
--------------------
Combina mapa pintado com:
  - Texto "LÁ DE {CIDADE}" em caixa alta (font Kesong)
  - Sublinhado com círculo na ponta (lado oposto à cidade)
  - Linha conectando sublinhado ao centroide do município

Regra da linha:
  - Cidade à ESQUERDA do centro: linha parte do INÍCIO (esquerda) do nome
  - Cidade à DIREITA do centro: linha parte do FIM (direita) do nome
  O círculo fica sempre no lado oposto (longe da cidade).

Saída: saida/{UF}/{nome}_arte_branco.png
        saida/{UF}/{nome}_arte_preto.png
"""

import csv
import io
import os
import sys
import unicodedata
from pathlib import Path

import cairosvg
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def _assets_dir() -> Path:
    return Path(
        os.environ.get(
            "ASSETS_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "assets"),
        )
    )


def _output_root() -> Path:
    return Path(
        os.environ.get(
            "OUTPUT_DIR",
            str(Path(__file__).resolve().parent.parent.parent / ".data" / "output"),
        )
    )


PASTA_SAIDA = _output_root() / "completa_cli"
ARQUIVO_CSV = Path(__file__).resolve().parent / "cidades_pendentes.csv"
FONT_PATH = _assets_dir() / "font" / "xiangcui-kesong" / "kesong-latest.ttf"
TEMPLATE_SVG = _assets_dir() / "arte-completa" / "templatelimpo.svg"

_template_img_cache: Image.Image | None = None

# ─── Canvas ────────────────────────────────────────────────────────────────────
CANVAS_W     = 4270
CANVAS_H     = 4900

def _carregar_template():
    import re

    svg = TEMPLATE_SVG.read_text(encoding="utf-8")
    # Remove os paths de fundo (branco e verde) — mantém só os pontos amarelos
    svg = re.sub(r'<path fill="#ffffff"[^/]*/>', '', svg)
    svg = re.sub(r'<path fill="#6fac7a"[^/]*/>', '', svg)
    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode(), output_width=CANVAS_W, output_height=CANVAS_H
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _template_img() -> Image.Image:
    global _template_img_cache
    if _template_img_cache is None:
        _template_img_cache = _carregar_template()
    return _template_img_cache

# ─── Configuração por estado (medido das referências) ─────────────────────────
# vis_x, vis_y = offset do conteúdo visível no canvas
# vis_w        = largura alvo do conteúdo visível
# cor_branco, cor_preto = cor da linha de identificação
UF_CONFIG = {
    'SC': dict(vis_x=373, vis_y=590, vis_w=3544, cor_b=(214,186,141,255), cor_p=(77, 84, 61, 255)),
    'PR': dict(vis_x=383, vis_y=544, vis_w=3609, cor_b=(214,186,141,255), cor_p=(77, 84, 61, 255)),
    'RS': dict(vis_x=501, vis_y=575, vis_w=3307, cor_b=(214,186,141,255), cor_p=(77, 84, 61, 255)),
    'GO': dict(vis_x=625, vis_y=557, vis_w=3029, cor_b=(227,154,45, 255), cor_p=(90, 46, 27, 255)),
    'MS': dict(vis_x=579, vis_y=564, vis_w=3160, cor_b=(227,154,45, 255), cor_p=(90, 46, 27, 255)),
    'MT': dict(vis_x=622, vis_y=550, vis_w=3057, cor_b=(227,154,45, 255), cor_p=(90, 46, 27, 255)),
    'DF': dict(vis_x=700, vis_y=557, vis_w=2900, cor_b=(227,154,45, 255), cor_p=(90, 46, 27, 255)),
    # Norte (cor_b=#A8C686, cor_p=#2F5D73)
    'AC': dict(vis_x=344, vis_y=661, vis_w=3716, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    'AM': dict(vis_x=239, vis_y=665, vis_w=3779, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    'AP': dict(vis_x=758, vis_y=660, vis_w=2594, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    'PA': dict(vis_x=708, vis_y=662, vis_w=3063, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    'RO': dict(vis_x=344, vis_y=669, vis_w=3527, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    'RR': dict(vis_x=741, vis_y=667, vis_w=2624, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    'TO': dict(vis_x=1231, vis_y=664, vis_w=1817, cor_b=(168,198,134,255), cor_p=(47,93,115,255)),
    # Sudeste (cor_b=terracota, cor_p=marrom-avermelhado)
    'MG': dict(vis_x=400,  vis_y=560, vis_w=3300, cor_b=(210,120, 80,255), cor_p=(90, 35, 25,255)),
    'SP': dict(vis_x=400,  vis_y=560, vis_w=3300, cor_b=(210,120, 80,255), cor_p=(90, 35, 25,255)),
    'RJ': dict(vis_x=400,  vis_y=560, vis_w=3300, cor_b=(210,120, 80,255), cor_p=(90, 35, 25,255)),
    'ES': dict(vis_x=400,  vis_y=560, vis_w=3300, cor_b=(210,120, 80,255), cor_p=(90, 35, 25,255)),
}
_DEFAULT_UF = dict(vis_x=373, vis_y=590, vis_w=3544, cor_b=(214,186,141,255), cor_p=(77,84,61,255))

# ─── Texto ─────────────────────────────────────────────────────────────────────
FONT_SIZE    = 230
TEXT_TOP_Y   = 50    # margem superior do texto no canvas
MAX_TEXT_W   = 3600  # largura máxima de uma linha de texto
PREFIX       = "LÁ DE "  # padrão; sobrescrito por --prefixo na CLI

# ─── Linha / círculo ───────────────────────────────────────────────────────────
LINE_WIDTH      = 11
CIRCLE_RADIUS   = 20
UNDERLINE_GAP   = 8    # gap entre o bottom do texto e o sublinhado
LINE_EXT        = 50   # extensão horizontal no lado do círculo

# ─── Cores fixas de texto ──────────────────────────────────────────────────────
COR_TEXTO_BRANCO = (242, 240, 239, 255)
COR_TEXTO_PRETO  = (0,   0,   0,   255)


# ─── Utilitários ───────────────────────────────────────────────────────────────

def normalizar_nome(nome):
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.lower().strip().replace('-', ' ')

def nome_arquivo(nome_oficial):
    return normalizar_nome(nome_oficial).replace(' ', '_')

def carregar_fonte(size=FONT_SIZE):
    return ImageFont.truetype(str(FONT_PATH), size)

def _draw():
    return ImageDraw.Draw(Image.new("RGBA", (1, 1)))

def medir_w(texto, font):
    bb = _draw().textbbox((0, 0), texto, font=font)
    return bb[2] - bb[0]

def medir_bbox(texto, font):
    return _draw().textbbox((0, 0), texto, font=font)


# ─── Mapa: escala e posição ────────────────────────────────────────────────────

def preparar_mapa(map_path, uf):
    """
    Lê o arquivo de mapa, recorta ao conteúdo visível, escala conforme config do UF
    e retorna (img_scaled, canvas_offset_x, canvas_offset_y).
    """
    cfg = UF_CONFIG.get(uf, _DEFAULT_UF)
    vis_x, vis_y, vis_w = cfg['vis_x'], cfg['vis_y'], cfg['vis_w']

    img = Image.open(map_path).convert("RGBA")
    arr = np.array(img)
    vis = arr[:, :, 3] > 10
    ys, xs = np.where(vis)

    if len(xs) == 0:
        return img, vis_x, vis_y

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())

    cropped = img.crop((x0, y0, x1 + 1, y1 + 1))
    scale   = vis_w / (x1 - x0 + 1)
    new_w   = vis_w
    new_h   = int(round((y1 - y0 + 1) * scale))
    scaled  = cropped.resize((new_w, new_h), Image.LANCZOS)

    return scaled, vis_x, vis_y


# ─── Centroide do município ────────────────────────────────────────────────────

def _geo_para_pixel(lon, lat, geo_bounds, vis_bounds):
    min_lon, max_lon, min_lat, max_lat = geo_bounds
    px_x0, px_y0, px_x1, px_y1 = vis_bounds
    norm_lon = (lon - min_lon) / (max_lon - min_lon)
    norm_lat = (max_lat - lat) / (max_lat - min_lat)
    return (px_x0 + norm_lon * (px_x1 - px_x0),
            px_y0 + norm_lat * (px_y1 - px_y0))

def _obter_vis_bounds_rgba(map_path):
    img = Image.open(map_path).convert('RGBA')
    arr = np.array(img)
    vis = arr[:, :, 3] > 10
    ys, xs = np.where(vis)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

def centroide_via_svg(nome_cidade, uf):
    """
    Retorna (cx, cy) em coords do PNG pintado.
    Usa o MESMO algoritmo de matching que pintar_municipio.py:
    1. Tenta por inkscape:label
    2. Usa bounds geográficos → SVG com score IoU + tamanho + distância
    3. Retorna centroide EXATO do path selecionado
    """
    import re
    import unicodedata as ud
    from lxml import etree

    from engine.utils.pintar_municipio import (
        encontrar_path_por_label,
        encontrar_path_por_bounds,
        converter_bounds_geo_para_svg,
        extrair_viewbox,
        extrair_transform_do_layer,
        calcular_centroide_path,
        calcular_extent_paths,
    )

    def norm(s):
        s = ud.normalize('NFKD', s)
        return ''.join(c for c in s if not ud.combining(c)).lower().strip()

    svg_file = _assets_dir() / "svg_estados" / f"{uf}_branco.svg"
    if not svg_file.exists():
        raise FileNotFoundError(f"SVG não encontrado: {svg_file}")

    tree = etree.parse(str(svg_file))
    viewbox = extrair_viewbox(tree)
    transform = extrair_transform_do_layer(tree)
    tx, ty = transform

    # State geographic bounds (qualidade minima para velocidade)
    coords_est = []
    def _walk(obj):
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                coords_est.append((obj[0], obj[1]))
            else:
                for i in obj: _walk(i)
        elif isinstance(obj, dict):
            for v in obj.values(): _walk(v)
    _walk(requests.get(
        f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
        "?formato=application/vnd.geo+json&qualidade=minima",
        timeout=30).json())
    lons_est = [c[0] for c in coords_est]
    lats_est = [c[1] for c in coords_est]
    bounds_estado = {
        'min_lon': min(lons_est), 'max_lon': max(lons_est),
        'min_lat': min(lats_est), 'max_lat': max(lats_est),
    }

    # Municipality IBGE code
    muns = requests.get(
        f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
        timeout=20).json()
    codigo = next((m["id"] for m in muns if norm(m["nome"]) == norm(nome_cidade)), None)
    if not codigo:
        raise ValueError(f"Código IBGE não encontrado: {nome_cidade}/{uf}")

    # Municipality geographic bounds
    coords_mun = []
    def _walk2(obj):
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                coords_mun.append((obj[0], obj[1]))
            else:
                for i in obj: _walk2(i)
        elif isinstance(obj, dict):
            for v in obj.values(): _walk2(v)
    _walk2(requests.get(
        f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}"
        "?formato=application/vnd.geo+json&qualidade=minima",
        timeout=20).json())
    lons_mun = [c[0] for c in coords_mun]
    lats_mun = [c[1] for c in coords_mun]
    bounds_municipio = {
        'min_lon': min(lons_mun), 'max_lon': max(lons_mun),
        'min_lat': min(lats_mun), 'max_lat': max(lats_mun),
        'center_lon': (min(lons_mun) + max(lons_mun)) / 2,
        'center_lat': (min(lats_mun) + max(lats_mun)) / 2,
    }

    # Mesmo critério de pintar_municipio: usa extent real quando não há labels
    tem_labels = any(
        p.get('{http://www.inkscape.org/namespaces/inkscape}label')
        for p in tree.xpath('//*[local-name()="path"]')
    )
    svg_extent = None if tem_labels else calcular_extent_paths(tree)

    # 1. Tenta pelo label (estados com inkscape:label)
    path_el, pontos = encontrar_path_por_label(tree, nome_cidade)

    # 2. Bounds matching: só para SVGs SEM labels (ex: alguns estados do Norte/CO).
    #    Para SVGs com labels, o bounds matching tende a encontrar o path errado
    #    quando o município não está rotulado — nesse caso, falha aqui e o chamador
    #    usa encontrar_centroide_no_mapa (centroide geográfico IBGE, mais preciso).
    if path_el is None and not tem_labels:
        bounds_svg = converter_bounds_geo_para_svg(
            bounds_municipio, bounds_estado, viewbox, transform, offset=(0, 0),
            svg_extent=svg_extent)
        if bounds_svg:
            path_el, pontos = encontrar_path_por_bounds(tree, bounds_svg, viewbox)

    if not pontos:
        raise ValueError(f"Path não encontrado no SVG para {nome_cidade}/{uf}")

    # Centroide ponderado pela área (Shoelace) — mais preciso que média de vértices
    # para polígonos irregulares como municípios.
    def _centroide_area(pts):
        n = len(pts)
        if n < 3:
            return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
        area = 0.0
        cx = 0.0
        cy = 0.0
        for i in range(n):
            j = (i + 1) % n
            cross = pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
            area += cross
            cx   += (pts[i][0] + pts[j][0]) * cross
            cy   += (pts[i][1] + pts[j][1]) * cross
        area *= 0.5
        if abs(area) < 1e-9:  # degenerate polygon — fallback to vertex mean
            return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
        cx /= (6.0 * area)
        cy /= (6.0 * area)
        return cx, cy

    raw_cx, raw_cy = _centroide_area(pontos)
    cx = raw_cx + tx
    cy = raw_cy + ty
    return int(cx), int(cy)


def encontrar_centroide_no_mapa(nome_cidade, uf, map_path):
    """
    Retorna (cx, cy) em coords do arquivo original.

    Usa o centroide geográfico do GeoJSON IBGE (a mesma fonte usada para pintar),
    projetado linearmente para o espaço de pixels do PNG via bounds do estado.
    Fallback: centroide dos pixels visíveis do PNG.
    """
    import requests, unicodedata as ud

    def norm(s):
        s = ud.normalize('NFKD', s)
        return ''.join(c for c in s if not ud.combining(c)).lower().strip()

    try:
        # 1. Código IBGE
        url_mun = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
        muns    = requests.get(url_mun, timeout=20).json()
        codigo  = next((m["id"] for m in muns if norm(m["nome"]) == norm(nome_cidade)), None)
        if not codigo:
            raise ValueError(f"código IBGE não encontrado para {nome_cidade}/{uf}")

        # 2. Centroide do GeoJSON do município
        url_gj  = (f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}"
                   "?formato=application/vnd.geo+json&qualidade=minima")
        gj_mun  = requests.get(url_gj, timeout=20).json()

        coords = []
        def _walk(obj):
            if isinstance(obj, list):
                if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                    coords.append((obj[0], obj[1]))
                else:
                    for item in obj: _walk(item)
            elif isinstance(obj, dict):
                for v in obj.values(): _walk(v)
        _walk(gj_mun)

        if not coords:
            raise ValueError("GeoJSON sem coordenadas")

        centroide_lon = sum(c[0] for c in coords) / len(coords)
        centroide_lat = sum(c[1] for c in coords) / len(coords)

        # 3. Bounds geográficos do estado
        url_est = (f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
                   "?formato=application/vnd.geo+json&qualidade=minima")
        gj_est     = requests.get(url_est, timeout=30).json()
        coords_est = []
        def _walk_est(obj):
            if isinstance(obj, list):
                if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                    coords_est.append((obj[0], obj[1]))
                else:
                    for item in obj: _walk_est(item)
            elif isinstance(obj, dict):
                for v in obj.values(): _walk_est(v)
        _walk_est(gj_est)
        lons = [c[0] for c in coords_est]
        lats = [c[1] for c in coords_est]
        if not lons:
            raise ValueError("GeoJSON do estado sem coordenadas")
        geo_bounds = (min(lons), max(lons), min(lats), max(lats))

        # 4. Bounds visíveis do PNG
        vis_bounds = _obter_vis_bounds_rgba(map_path)

        # 5. Projeta centroide geográfico → pixel
        cx, cy = _geo_para_pixel(centroide_lon, centroide_lat, geo_bounds, vis_bounds)
        return int(cx), int(cy)

    except Exception as e:
        print(f"  ⚠️  Centroide via IBGE falhou ({e}), usando fallback visual")
        img = Image.open(map_path).convert('RGBA')
        arr = np.array(img)
        vis = arr[:, :, 3] > 10
        ys, xs = np.where(vis)
        if len(xs) == 0:
            h, w = arr.shape[:2]
            return w // 2, h // 2
        return int(xs.mean()), int(ys.mean())


def centroide_no_canvas(map_path, scaled_map, map_cx, map_cy, vis_x, vis_y):
    """
    Converte o centroide do arquivo original para coordenadas do canvas.
    """
    orig = Image.open(map_path).convert("RGBA")
    arr  = np.array(orig)
    vis  = arr[:, :, 3] > 10
    ys, xs = np.where(vis)
    x0, y0 = int(xs.min()), int(ys.min())
    x1, y1 = int(xs.max()), int(ys.max())
    scale_x = scaled_map.width  / (x1 - x0 + 1)
    scale_y = scaled_map.height / (y1 - y0 + 1)

    cx_canvas = vis_x + int((map_cx - x0) * scale_x)
    cy_canvas = vis_y + int((map_cy - y0) * scale_y)
    return cx_canvas, cy_canvas


# ─── Layout do texto ───────────────────────────────────────────────────────────

def calcular_linhas(nome_cidade, font, prefix=None):
    """
    Retorna lista de (texto, is_cidade_text, x_sub_ini, x_sub_fim).
    A linha com is_cidade_text=True é a última e recebe o sublinhado.

    Lógica:
      1. Tudo em uma linha se couber
      2. "LÁ DE" + cidade em linhas separadas se cidade couber sozinha
      3. Divide o nome da cidade ao melhor ponto e usa "LÁ DE {parte1}" / "{parte2}"
    """
    pfx     = (prefix.rstrip() + " ") if prefix else PREFIX
    nome_up = nome_cidade.upper()
    full    = pfx + nome_up

    def w(t):
        return medir_w(t, font)

    def x_of_line(texto):
        """x esquerda de um texto centrado em CANVAS_W."""
        return (CANVAS_W - w(texto)) // 2

    # Opção 1: linha única
    if w(full) <= MAX_TEXT_W:
        x_l = x_of_line(full)
        x_c_ini = x_l + w(pfx)
        x_c_fim = x_l + w(full)
        return [(full, True, x_c_ini, x_c_fim)]

    # Opção 2: prefixo / cidade
    prefix_bare = pfx.strip()
    if w(nome_up) <= MAX_TEXT_W:
        x_ini = x_of_line(nome_up)
        x_fim = x_ini + w(nome_up)
        return [
            (prefix_bare, False, 0, 0),
            (nome_up,     True,  x_ini, x_fim),
        ]

    # Opção 3: "{pfx}{p1}" / "{p2}" — divide o nome
    palavras    = nome_up.split()
    best_split  = None
    best_diff   = float('inf')
    for i in range(1, len(palavras)):
        p1 = ' '.join(palavras[:i])
        p2 = ' '.join(palavras[i:])
        full1 = pfx + p1
        diff  = abs(w(full1) - w(p2))
        if diff < best_diff:
            best_diff  = diff
            best_split = (p1, p2)

    p1, p2  = best_split
    linha1  = pfx + p1
    linha2  = p2
    x_ini2  = x_of_line(linha2)
    x_fim2  = x_ini2 + w(linha2)
    return [
        (linha1, False, 0, 0),
        (linha2, True,  x_ini2, x_fim2),
    ]


def calcular_y(linhas, font):
    """
    Retorna (lista_y_ancora, y_bottom_ultima_linha).
    """
    _, ink_h, _ = medir_bbox(linhas[0][0], font), medir_bbox(linhas[0][0], font)[3] - medir_bbox(linhas[0][0], font)[1], None
    ink_h = medir_bbox(linhas[0][0], font)[3] - medir_bbox(linhas[0][0], font)[1]
    n       = len(linhas)
    gap     = int(ink_h * 0.20)
    ys      = [TEXT_TOP_Y + ink_h // 2 + i * (ink_h + gap) for i in range(n)]
    y_bot   = TEXT_TOP_Y + n * ink_h + (n - 1) * gap
    return ys, y_bot


# ─── Linha de identificação ─────────────────────────────────────────────────────

def desenhar_linha(draw, city_cx, city_cy, x_sub_ini, x_sub_fim, y_sub, cor):
    """
    Desenha sublinhado + linha de conexão + círculos.
    Direção depende de se a cidade está à esquerda ou direita do centro.
    """
    cidade_esquerda = city_cx < CANVAS_W // 2

    if cidade_esquerda:
        # Linha parte do INÍCIO (esquerda) do nome, círculo no FIM (direita)
        x_connect = x_sub_ini          # ponto que vai para a cidade
        x_circle  = x_sub_fim + LINE_EXT  # círculo oposto
    else:
        # Linha parte do FIM (direita) do nome, círculo no INÍCIO (esquerda)
        x_connect = x_sub_fim + LINE_EXT  # ponto que vai para a cidade
        x_circle  = x_sub_ini          # círculo oposto

    # Sublinhado completo (de ponta a ponta incluindo extensão)
    draw.line([(x_sub_ini, y_sub), (x_sub_fim + LINE_EXT, y_sub)],
              fill=cor, width=LINE_WIDTH)

    # Diagonal: ponto de conexão → centroide
    draw.line([(x_connect, y_sub), (city_cx, city_cy)],
              fill=cor, width=LINE_WIDTH)

    # Círculos
    r = CIRCLE_RADIUS
    draw.ellipse([x_circle - r, y_sub - r, x_circle + r, y_sub + r], fill=cor)
    draw.ellipse([city_cx - r, city_cy - r, city_cx + r, city_cy + r], fill=cor)


# ─── Geração da arte ──────────────────────────────────────────────────────────

def gerar_arte(
    nome_ibge,
    uf,
    map_branco_path,
    map_preto_path,
    pasta_destino,
    nome_base,
    prefix=None,
    nome_exibicao=None,
):
    pasta_destino.mkdir(parents=True, exist_ok=True)
    font = carregar_fonte()
    cfg = UF_CONFIG.get(uf, _DEFAULT_UF)
    nome_txt = nome_exibicao or nome_ibge

    # Prepara o mapa com config do estado
    scaled_b, off_x, off_y = preparar_mapa(map_branco_path, uf)
    scaled_p, _, _ = preparar_mapa(map_preto_path, uf)

    # Centroide do município no canvas (via path SVG — coordenadas exatas)
    try:
        cx_file, cy_file = centroide_via_svg(nome_ibge, uf)
    except Exception as e:
        print(f"  ⚠️  SVG centroid falhou ({e}), usando IBGE GeoJSON")
        cx_file, cy_file = encontrar_centroide_no_mapa(nome_ibge, uf, map_branco_path)
    city_cx, city_cy = centroide_no_canvas(
        map_branco_path, scaled_b, cx_file, cy_file, off_x, off_y
    )

    # Layout do texto (nome amigável na loja, não necessariamente o oficial IBGE)
    linhas = calcular_linhas(nome_txt, font, prefix=prefix)
    ys_ancora, y_bot = calcular_y(linhas, font)
    y_sub            = y_bot + UNDERLINE_GAP

    linha_sub = next(l for l in reversed(linhas) if l[1])
    x_sub_ini = linha_sub[2]
    x_sub_fim = linha_sub[3]

    gerados = []
    variantes = [
        ("branco", scaled_b, COR_TEXTO_BRANCO, cfg['cor_b']),
        ("preto",  scaled_p, COR_TEXTO_PRETO,  cfg['cor_p']),
    ]

    for variante, scaled_map, cor_texto, cor_linha in variantes:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        canvas.paste(scaled_map, (off_x, off_y), scaled_map)

        draw = ImageDraw.Draw(canvas)

        for (texto, _, _, _), y_a in zip(linhas, ys_ancora):
            draw.text((CANVAS_W // 2, y_a), texto, font=font, fill=cor_texto, anchor='mm')

        desenhar_linha(draw, city_cx, city_cy, x_sub_ini, x_sub_fim, y_sub, cor_linha)

        # Pontos amarelos do template por cima (preserva transparência)
        canvas = Image.alpha_composite(canvas, _template_img())

        saida = pasta_destino / f"{nome_base}_arte_{variante}.png"
        canvas.save(str(saida), "PNG")
        print(f"  ✅ {saida}")
        gerados.append(str(saida))

    return gerados


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cidade", help="'Cidade,UF'")
    parser.add_argument("--uf")
    parser.add_argument("--prefixo", help="Prefixo customizado, ex: 'LÁ DA' ou 'LÁ DO'")
    args = parser.parse_args()

    if args.cidade:
        if ',' not in args.cidade:
            print("❌ Use 'Cidade,UF'")
            sys.exit(1)
        cidade, uf = args.cidade.rsplit(',', 1)
        cidade, uf = cidade.strip(), uf.strip().upper()

        from engine.utils.coordenadas import buscar_codigo_ibge
        _, nome_oficial = buscar_codigo_ibge(uf, cidade)
        if not nome_oficial:
            nome_oficial = cidade
        n_arq    = nome_arquivo(nome_oficial)
        pasta_uf = PASTA_SAIDA / uf
        map_b    = pasta_uf / f"{n_arq}_branco.png"
        map_p    = pasta_uf / f"{n_arq}_preto.png"

        if not map_b.exists():
            print(f"❌ Mapa não encontrado: {map_b}")
            sys.exit(1)

        print(f"🎨 {nome_oficial}/{uf}")
        gerar_arte(nome_oficial, uf, map_b, map_p, pasta_uf, n_arq, prefix=args.prefixo)
        return

    cidades = []
    with open(ARQUIVO_CSV, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            cidade = row['cidade'].strip()
            uf     = row['uf'].strip().strip('"').upper()
            if args.uf and uf != args.uf.upper():
                continue
            cidades.append((cidade, uf))

    total = len(cidades)
    erros = 0
    for i, (cidade, uf) in enumerate(cidades):
        print(f"\n[{i+1}/{total}] {cidade}/{uf}")
        try:
            from engine.utils.coordenadas import buscar_codigo_ibge
            _, nome_oficial = buscar_codigo_ibge(uf, cidade)
            if not nome_oficial:
                nome_oficial = cidade
            n_arq    = nome_arquivo(nome_oficial)
            pasta_uf = PASTA_SAIDA / uf
            map_b    = pasta_uf / f"{n_arq}_branco.png"
            map_p    = pasta_uf / f"{n_arq}_preto.png"
            if not map_b.exists():
                print(f"  ❌ Mapa não encontrado")
                erros += 1
                continue
            gerar_arte(nome_oficial, uf, map_b, map_p, pasta_uf, n_arq)
        except Exception as e:
            import traceback; traceback.print_exc()
            erros += 1

    print(f"\n✅ {total - erros} gerados | {erros} erros")


if __name__ == "__main__":
    main()
