#!/usr/bin/env python3
"""
Processar Cidades Pendentes
---------------------------
Lê cidades_pendentes.csv e gera PNGs (preto e branco) para cada cidade.

Melhorias sobre pintar_municipio.py:
- Aplica transforms acumulados de TODOS os grupos SVG (não só layer1)
- Usa o extent real dos paths do SVG para calibrar geo→SVG (sem margem hardcoded)
- Não depende de referências geográficas hardcoded (funciona para todos os estados)
- Cache de bounds por estado e por SVG para evitar reprocessamento
- Pula cidades já geradas, suporta filtro por UF e range de índices
"""

import os
import re
import sys
import csv
import math
import requests
import unicodedata
from pathlib import Path
from lxml import etree
import cairosvg

_ROOT = Path(__file__).resolve().parent.parent.parent
_ASSETS = Path(os.environ.get("ASSETS_DIR", str(_ROOT / "assets")))
PASTA_BASE = _ROOT
PASTA_SVG = _ASSETS / "svg_estados"
PASTA_SVG.mkdir(parents=True, exist_ok=True)
_OUTPUT = Path(os.environ.get("OUTPUT_DIR", str(_ROOT / ".data" / "output")))
PASTA_SAIDA = _OUTPUT / "svg_pendentes_tmp"
PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
ARQUIVO_PENDENTES = PASTA_BASE / "cidades_pendentes.csv"

# Caches em memória
_cache_bounds_estado = {}       # uf -> bounds
_cache_municipios_uf = {}       # uf -> lista de municípios
_cache_bounds_svg = {}          # str(svg_path) -> bounds_svg_real
_cache_paths_svg = {}           # str(svg_path) -> lista de path_info


# ─── Normalização de nomes ───────────────────────────────────────────────────

def normalizar_nome(nome):
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.lower().strip().replace('-', ' ')


# ─── API IBGE ─────────────────────────────────────────────────────────────────

def buscar_svg_estado(uf, variante):
    nome_esperado = f"{uf.lower()}_{variante.lower()}.svg"
    if not PASTA_SVG.exists():
        return None
    for arquivo in PASTA_SVG.iterdir():
        if arquivo.is_file() and arquivo.name.lower() == nome_esperado:
            return arquivo
    return None


def buscar_codigo_ibge(uf, cidade):
    if uf not in _cache_municipios_uf:
        url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                _cache_municipios_uf[uf] = r.json()
            else:
                _cache_municipios_uf[uf] = []
        except Exception as e:
            print(f"   ⚠️ Erro ao buscar municípios de {uf}: {e}")
            _cache_municipios_uf[uf] = []

    cidade_norm = normalizar_nome(cidade)
    for m in _cache_municipios_uf.get(uf, []):
        if normalizar_nome(m["nome"]) == cidade_norm:
            return m["id"], m["nome"]
    return None, None


def baixar_geojson_municipio(codigo):
    url = (f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}"
           f"?formato=application/vnd.geo+json")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"   ⚠️ Erro ao baixar GeoJSON: {e}")
    return None


def extrair_todas_coordenadas(geojson):
    coords = []

    def _extrair(obj):
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                coords.append((obj[0], obj[1]))
            else:
                for item in obj:
                    _extrair(item)
        elif isinstance(obj, dict):
            for chave in ("coordinates", "geometry", "features"):
                if chave in obj:
                    _extrair(obj[chave])
                    break

    _extrair(geojson)
    return coords


def calcular_bounds_coords(coords):
    if not coords:
        return None
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return {
        "min_lon": min(lons), "max_lon": max(lons),
        "min_lat": min(lats), "max_lat": max(lats),
        "center_lon": (min(lons) + max(lons)) / 2,
        "center_lat": (min(lats) + max(lats)) / 2,
    }


def baixar_bounds_estado(uf):
    if uf in _cache_bounds_estado:
        return _cache_bounds_estado[uf]

    try:
        r = requests.get(
            "https://servicodados.ibge.gov.br/api/v1/localidades/estados", timeout=30
        )
        if r.status_code != 200:
            return None
        estados = r.json()
        codigo_uf = next(
            (e["id"] for e in estados if e["sigla"].upper() == uf.upper()), None
        )
        if not codigo_uf:
            return None

        url = (f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo_uf}"
               f"?formato=application/vnd.geo+json")
        r2 = requests.get(url, timeout=60)
        if r2.status_code == 200:
            coords = extrair_todas_coordenadas(r2.json())
            bounds = calcular_bounds_coords(coords)
            _cache_bounds_estado[uf] = bounds
            return bounds
    except Exception as e:
        print(f"   ⚠️ Erro ao baixar bounds do estado: {e}")
    return None


# ─── Transforms SVG ───────────────────────────────────────────────────────────

def parse_transform(t_str):
    """Converte string de transform SVG para matriz [a,b,c,d,e,f]."""
    if not t_str:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    # matrix(a,b,c,d,e,f)
    m = re.search(
        r'matrix\(\s*([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+'
        r'([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([-\d.eE+]+)\s*\)', t_str
    )
    if m:
        return tuple(float(m.group(i)) for i in range(1, 7))

    # translate(tx) ou translate(tx, ty)
    m = re.search(
        r'translate\(\s*([-\d.eE+]+)(?:[\s,]+([-\d.eE+]+))?\s*\)', t_str
    )
    if m:
        tx = float(m.group(1))
        ty = float(m.group(2)) if m.group(2) else 0.0
        return (1.0, 0.0, 0.0, 1.0, tx, ty)

    # scale(sx) ou scale(sx, sy)
    m = re.search(
        r'scale\(\s*([-\d.eE+]+)(?:[\s,]+([-\d.eE+]+))?\s*\)', t_str
    )
    if m:
        sx = float(m.group(1))
        sy = float(m.group(2)) if m.group(2) else sx
        return (sx, 0.0, 0.0, sy, 0.0, 0.0)

    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def compor_transforms(t_externo, t_interno):
    """Compõe dois transforms: t_externo aplicado primeiro."""
    a1, b1, c1, d1, e1, f1 = t_externo
    a2, b2, c2, d2, e2, f2 = t_interno
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def aplicar_transform(ponto, t):
    a, b, c, d, e, f = t
    x, y = ponto
    return (a * x + c * y + e, b * x + d * y + f)


def construir_mapa_pais(svg_tree):
    mapa = {}
    for elem in svg_tree.iter():
        for filho in elem:
            mapa[id(filho)] = elem
    return mapa


def obter_transform_acumulado(elemento, mapa_pais):
    """Acumula transforms de todos os ancestrais (do mais externo para o elemento)."""
    cadeia = []
    elem = elemento
    while elem is not None:
        t_str = elem.get('transform', '')
        if t_str:
            cadeia.append(parse_transform(t_str))
        elem = mapa_pais.get(id(elem))

    resultado = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for t in reversed(cadeia):
        resultado = compor_transforms(resultado, t)
    return resultado


# ─── Parsing de paths SVG ─────────────────────────────────────────────────────

def parse_svg_path(d):
    """Extrai pontos representativos de um path SVG."""
    pontos = []
    d = d.replace(',', ' ')
    partes = re.split(r'([MmLlHhVvCcSsQqTtAaZz])', d)
    x, y = 0.0, 0.0
    comando = 'M'

    i = 0
    while i < len(partes):
        parte = partes[i].strip()
        if parte in 'MmLlHhVvCcSsQqTtAaZz':
            comando = parte
            i += 1
            continue
        if not parte:
            i += 1
            continue

        nums = re.findall(r'-?[\d.]+(?:[eE][+-]?\d+)?', parte)

        j = 0
        while j < len(nums):
            try:
                if comando in 'Mm':
                    dx, dy = float(nums[j]), float(nums[j + 1])
                    x, y = (x + dx, y + dy) if comando == 'm' else (dx, dy)
                    pontos.append((x, y))
                    j += 2
                    comando = 'l' if comando == 'm' else 'L'
                elif comando in 'Ll':
                    dx, dy = float(nums[j]), float(nums[j + 1])
                    x, y = (x + dx, y + dy) if comando == 'l' else (dx, dy)
                    pontos.append((x, y))
                    j += 2
                elif comando in 'Hh':
                    dx = float(nums[j])
                    x = x + dx if comando == 'h' else dx
                    pontos.append((x, y))
                    j += 1
                elif comando in 'Vv':
                    dy = float(nums[j])
                    y = y + dy if comando == 'v' else dy
                    pontos.append((x, y))
                    j += 1
                elif comando in 'Cc':
                    if j + 5 < len(nums):
                        x, y = ((x + float(nums[j + 4]), y + float(nums[j + 5]))
                                if comando == 'c'
                                else (float(nums[j + 4]), float(nums[j + 5])))
                        pontos.append((x, y))
                    j += 6
                elif comando in 'Ss':
                    if j + 3 < len(nums):
                        x, y = ((x + float(nums[j + 2]), y + float(nums[j + 3]))
                                if comando == 's'
                                else (float(nums[j + 2]), float(nums[j + 3])))
                        pontos.append((x, y))
                    j += 4
                elif comando in 'Qq':
                    if j + 3 < len(nums):
                        x, y = ((x + float(nums[j + 2]), y + float(nums[j + 3]))
                                if comando == 'q'
                                else (float(nums[j + 2]), float(nums[j + 3])))
                        pontos.append((x, y))
                    j += 4
                elif comando in 'Tt':
                    if j + 1 < len(nums):
                        x, y = ((x + float(nums[j]), y + float(nums[j + 1]))
                                if comando == 't'
                                else (float(nums[j]), float(nums[j + 1])))
                        pontos.append((x, y))
                    j += 2
                elif comando in 'Aa':
                    if j + 6 < len(nums):
                        x, y = ((x + float(nums[j + 5]), y + float(nums[j + 6]))
                                if comando == 'a'
                                else (float(nums[j + 5]), float(nums[j + 6])))
                        pontos.append((x, y))
                    j += 7
                elif comando in 'Zz':
                    break
                else:
                    j += 1
            except (IndexError, ValueError):
                j += 1
        i += 1

    return pontos


def calcular_bounds_pontos(pontos):
    if not pontos:
        return None
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return {
        'min_x': min_x, 'max_x': max_x,
        'min_y': min_y, 'max_y': max_y,
        'width': max_x - min_x,
        'height': max_y - min_y,
        'center_x': (min_x + max_x) / 2,
        'center_y': (min_y + max_y) / 2,
    }


def ponto_em_poligono(x, y, pontos):
    if len(pontos) < 3:
        return False
    n = len(pontos)
    dentro = False
    j = n - 1
    for i in range(n):
        xi, yi = pontos[i]
        xj, yj = pontos[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            dentro = not dentro
        j = i
    return dentro


def distancia(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


# ─── Pré-processamento do SVG ─────────────────────────────────────────────────

def preprocessar_svg(svg_path_file):
    """
    Lê o SVG, calcula bounds reais (com transforms acumulados) e
    pré-computa uma lista de path_info para matching rápido.
    Resultado é cacheado por arquivo.
    """
    chave = str(svg_path_file)
    if chave in _cache_bounds_svg:
        return _cache_bounds_svg[chave], _cache_paths_svg[chave]

    print(f"      Pré-processando SVG: {svg_path_file.name} ...", flush=True)

    parser = etree.XMLParser(remove_blank_text=True)
    svg_tree = etree.parse(str(svg_path_file), parser)
    mapa_pais = construir_mapa_pais(svg_tree)

    paths_info = []
    all_xs = []
    all_ys = []

    for path_elem in svg_tree.xpath('//*[local-name()="path"]'):
        d = path_elem.get('d')
        if not d:
            continue
        pontos_raw = parse_svg_path(d)
        if len(pontos_raw) < 3:
            continue

        t = obter_transform_acumulado(path_elem, mapa_pais)
        pontos = [aplicar_transform(p, t) for p in pontos_raw]

        bounds = calcular_bounds_pontos(pontos)
        if not bounds:
            continue

        label = path_elem.get(
            '{http://www.inkscape.org/namespaces/inkscape}label', ''
        )

        # Identificadores estáveis para re-localizar o path após recarregar o SVG
        elem_id = path_elem.get('id', '')
        # Prefixo do atributo 'd' como assinatura (primeiros 80 chars são únicos na prática)
        d_prefix = d[:80]

        paths_info.append({
            'elem_id': elem_id,
            'd_prefix': d_prefix,
            'label': label,
            'bounds': bounds,
            'pontos': pontos,
        })

        all_xs.extend(p[0] for p in pontos)
        all_ys.extend(p[1] for p in pontos)

    if not all_xs:
        _cache_bounds_svg[chave] = None
        _cache_paths_svg[chave] = paths_info
        return None, paths_info

    bounds_svg_real = {
        'min_x': min(all_xs), 'max_x': max(all_xs),
        'min_y': min(all_ys), 'max_y': max(all_ys),
        'width': max(all_xs) - min(all_xs),
        'height': max(all_ys) - min(all_ys),
    }

    print(f"      SVG real: x({bounds_svg_real['min_x']:.0f},{bounds_svg_real['max_x']:.0f})"
          f" y({bounds_svg_real['min_y']:.0f},{bounds_svg_real['max_y']:.0f})"
          f" ({len(paths_info)} paths)")

    _cache_bounds_svg[chave] = bounds_svg_real
    _cache_paths_svg[chave] = paths_info
    return bounds_svg_real, paths_info


# ─── Conversão geo → SVG ──────────────────────────────────────────────────────

def geo_para_svg(lon, lat, bounds_estado, bounds_svg_real):
    """
    Converte coordenadas geográficas para coordenadas SVG canvas usando o
    extent real dos paths (sem margem fixa assumida).
    """
    lon_range = bounds_estado['max_lon'] - bounds_estado['min_lon']
    lat_range = bounds_estado['max_lat'] - bounds_estado['min_lat']

    if lon_range == 0 or lat_range == 0 or not bounds_svg_real:
        return None

    norm_lon = (lon - bounds_estado['min_lon']) / lon_range
    norm_lat = (bounds_estado['max_lat'] - lat) / lat_range   # Y invertido no SVG

    svg_x = bounds_svg_real['min_x'] + norm_lon * bounds_svg_real['width']
    svg_y = bounds_svg_real['min_y'] + norm_lat * bounds_svg_real['height']
    return (svg_x, svg_y)


def calcular_bounds_municipio_em_svg(bounds_mun, bounds_estado, bounds_svg_real):
    """Converte bounds geográficos do município para espaço SVG canvas."""
    p_min = geo_para_svg(bounds_mun['min_lon'], bounds_mun['max_lat'],
                         bounds_estado, bounds_svg_real)
    p_max = geo_para_svg(bounds_mun['max_lon'], bounds_mun['min_lat'],
                         bounds_estado, bounds_svg_real)
    if not p_min or not p_max:
        return None

    min_x = min(p_min[0], p_max[0])
    max_x = max(p_min[0], p_max[0])
    min_y = min(p_min[1], p_max[1])
    max_y = max(p_min[1], p_max[1])

    return {
        'min_x': min_x, 'max_x': max_x,
        'min_y': min_y, 'max_y': max_y,
        'width': max_x - min_x,
        'height': max_y - min_y,
        'center_x': (min_x + max_x) / 2,
        'center_y': (min_y + max_y) / 2,
    }


# ─── Matching de paths ────────────────────────────────────────────────────────

def calcular_iou(b1, b2):
    ix1 = max(b1['min_x'], b2['min_x'])
    ix2 = min(b1['max_x'], b2['max_x'])
    iy1 = max(b1['min_y'], b2['min_y'])
    iy2 = min(b1['max_y'], b2['max_y'])
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    area1 = b1['width'] * b1['height']
    area2 = b2['width'] * b2['height']
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def encontrar_path_por_label(paths_info, nome_municipio):
    """Tenta encontrar o path pelo inkscape:label."""
    nome_norm = normalizar_nome(nome_municipio)
    for info in paths_info:
        if info['label'] and normalizar_nome(info['label']) == nome_norm:
            return info
    return None


def encontrar_melhor_path(paths_info, bounds_mun_svg, nome_municipio=None):
    """
    Encontra o path que melhor representa o município:
    1. Tenta pelo label (inkscape:label)
    2. Faz matching por IoU + similaridade de tamanho + distância ao centróide
    """
    # 1. Por label
    if nome_municipio:
        info = encontrar_path_por_label(paths_info, nome_municipio)
        if info:
            print(f"      ✓ Encontrado pelo label")
            return info

    # 2. Por scoring geométrico
    area_esperada = bounds_mun_svg['width'] * bounds_mun_svg['height']
    centro_esperado = (bounds_mun_svg['center_x'], bounds_mun_svg['center_y'])
    ref_size = max(bounds_mun_svg['width'] + bounds_mun_svg['height'], 1.0)

    candidatos = []
    for info in paths_info:
        b = info['bounds']
        area_path = b['width'] * b['height']

        # Filtra paths com tamanho muito discrepante
        if area_esperada > 0:
            ratio = area_path / area_esperada
            if ratio > 10.0 or ratio < 0.1:
                continue

        iou = calcular_iou(bounds_mun_svg, b)

        dist = distancia(centro_esperado, (b['center_x'], b['center_y']))
        dist_norm = dist / ref_size

        if max(b['width'], bounds_mun_svg['width']) > 0:
            w_ratio = min(b['width'], bounds_mun_svg['width']) / max(b['width'], bounds_mun_svg['width'])
        else:
            w_ratio = 0.0

        if max(b['height'], bounds_mun_svg['height']) > 0:
            h_ratio = min(b['height'], bounds_mun_svg['height']) / max(b['height'], bounds_mun_svg['height'])
        else:
            h_ratio = 0.0

        size_sim = (w_ratio + h_ratio) / 2.0
        score = iou * 0.4 + size_sim * 0.4 + (1.0 / (1.0 + dist_norm)) * 0.2

        candidatos.append({**info, 'iou': iou, 'dist': dist, 'size_sim': size_sim, 'score': score})

    if not candidatos:
        # Fallback: menor distância sem filtro de área
        for info in paths_info:
            b = info['bounds']
            dist = distancia(centro_esperado, (b['center_x'], b['center_y']))
            candidatos.append({**info, 'iou': 0.0, 'dist': dist, 'size_sim': 0.0, 'score': -dist})

    candidatos.sort(key=lambda c: -c['score'])
    melhor = candidatos[0]
    print(f"      Match: score={melhor['score']:.4f} IoU={melhor['iou']:.4f} "
          f"size={melhor['size_sim']:.2f} dist={melhor['dist']:.1f}")
    return melhor


# ─── Modificação do SVG e geração do PNG ──────────────────────────────────────

def extrair_cor_stroke(svg_tree):
    for path in svg_tree.xpath('//*[local-name()="path"]'):
        style = path.get('style', '')
        m = re.search(r'stroke:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)', style)
        if m:
            return m.group(1)
        stroke = path.get('stroke')
        if stroke:
            return stroke
    return '#000000'


def pintar_path_no_svg(svg_path_file, path_info, nome_saida, pasta_saida):
    """
    Carrega o SVG, localiza o path pela info de identificação e gera o PNG.
    Tenta localizar por: id → prefixo do atributo 'd' → label.
    """
    parser = etree.XMLParser(remove_blank_text=True)
    svg_tree = etree.parse(str(svg_path_file), parser)

    path_element = None

    # 1. Por id
    elem_id = path_info.get('elem_id', '')
    if elem_id:
        resultados = svg_tree.xpath(f'//*[@id="{elem_id}"]')
        if resultados:
            path_element = resultados[0]

    # 2. Por prefixo do atributo 'd'
    if path_element is None:
        d_prefix = path_info.get('d_prefix', '')
        if d_prefix:
            for p in svg_tree.xpath('//*[local-name()="path"]'):
                d = p.get('d', '')
                if d.startswith(d_prefix):
                    path_element = p
                    break

    # 3. Por label
    if path_element is None:
        label = path_info.get('label', '')
        if label:
            for p in svg_tree.xpath('//*[local-name()="path"]'):
                if p.get('{http://www.inkscape.org/namespaces/inkscape}label', '') == label:
                    path_element = p
                    break

    if path_element is None:
        print(f"      ⚠️ Não foi possível re-localizar o path no SVG")
        return None

    cor_original = extrair_cor_stroke(svg_tree)

    style_atual = path_element.get('style', '')
    if 'fill:' in style_atual:
        style_novo = re.sub(r'fill:[^;]+', f'fill:{cor_original}', style_atual)
    else:
        style_novo = style_atual + f';fill:{cor_original}'

    if 'fill-opacity:' in style_novo:
        style_novo = re.sub(r'fill-opacity:[^;]+', 'fill-opacity:1', style_novo)
    else:
        style_novo += ';fill-opacity:1'

    path_element.set('style', style_novo)

    pasta_saida.mkdir(parents=True, exist_ok=True)

    # Salva SVG temporário na pasta raiz de saída (evita conflito entre estados)
    svg_tmp = PASTA_SAIDA / f"{nome_saida}.svg"
    svg_tree.write(str(svg_tmp), encoding='UTF-8', xml_declaration=True)

    # Converte para PNG na pasta do estado
    png_saida = pasta_saida / f"{nome_saida}.png"
    with open(svg_tmp, 'rb') as f:
        conteudo = f.read()

    cairosvg.svg2png(bytestring=conteudo, write_to=str(png_saida), dpi=300)

    svg_tmp.unlink()
    return str(png_saida)


def processar_svg_para_municipio(svg_path_file, bounds_mun, bounds_estado, nome_arquivo, cor, nome_oficial, pasta_saida):
    """
    Fluxo completo para uma variante (preto/branco):
    1. Pré-processa o SVG (cached)
    2. Calcula bounds esperados do município em coords SVG
    3. Encontra o path correto
    4. Pinta e gera PNG
    """
    bounds_svg_real, paths_info = preprocessar_svg(svg_path_file)
    if not bounds_svg_real or not paths_info:
        print(f"      ❌ Falha ao pré-processar SVG")
        return None

    bounds_mun_svg = calcular_bounds_municipio_em_svg(bounds_mun, bounds_estado, bounds_svg_real)
    if not bounds_mun_svg:
        print(f"      ❌ Falha ao converter bounds do município")
        return None

    print(f"      Município SVG: x({bounds_mun_svg['min_x']:.0f},{bounds_mun_svg['max_x']:.0f})"
          f" y({bounds_mun_svg['min_y']:.0f},{bounds_mun_svg['max_y']:.0f})")

    melhor = encontrar_melhor_path(paths_info, bounds_mun_svg, nome_oficial)
    if not melhor:
        print(f"      ❌ Path não encontrado")
        return None

    nome_saida = f"{nome_arquivo}_{cor}"
    png = pintar_path_no_svg(svg_path_file, melhor, nome_saida, pasta_saida)
    if png:
        print(f"      ✅ {png}")
    return png


# ─── Processamento de municípios ──────────────────────────────────────────────

def processar_municipio(cidade, uf):
    print(f"\n{'='*60}")
    print(f"📍 {cidade}/{uf}")
    print(f"{'='*60}")

    svg_preto = buscar_svg_estado(uf, "preto")
    svg_branco = buscar_svg_estado(uf, "branco")

    if not svg_preto and not svg_branco:
        print(f"   ❌ SVGs do estado {uf} não encontrados em {PASTA_SVG}")
        return None

    codigo, nome_oficial = buscar_codigo_ibge(uf, cidade)
    if not codigo:
        print(f"   ❌ Município não encontrado no IBGE: {cidade}/{uf}")
        return None
    print(f"   ✅ IBGE: {codigo} – {nome_oficial}")

    # Pasta de saída por estado
    pasta_uf = PASTA_SAIDA / uf
    pasta_uf.mkdir(parents=True, exist_ok=True)

    nome_arquivo = normalizar_nome(nome_oficial).replace(' ', '_')
    png_preto = pasta_uf / f"{nome_arquivo}_preto.png"
    png_branco = pasta_uf / f"{nome_arquivo}_branco.png"

    preto_ok = png_preto.exists()
    branco_ok = png_branco.exists()

    if preto_ok and branco_ok:
        print(f"   ℹ️  Já gerado — pulando")
        return {"status": "ja_existia", "municipio": nome_oficial}

    geojson = baixar_geojson_municipio(codigo)
    if not geojson:
        print(f"   ❌ Falha ao baixar GeoJSON")
        return None

    coords_mun = extrair_todas_coordenadas(geojson)
    bounds_mun = calcular_bounds_coords(coords_mun)
    if not bounds_mun:
        print(f"   ❌ Falha ao calcular bounds do município")
        return None

    print(f"   Bounds: lon({bounds_mun['min_lon']:.3f},{bounds_mun['max_lon']:.3f})"
          f" lat({bounds_mun['min_lat']:.3f},{bounds_mun['max_lat']:.3f})")

    bounds_estado = baixar_bounds_estado(uf)
    if not bounds_estado:
        print(f"   ❌ Falha ao obter bounds do estado")
        return None

    resultados = []

    if svg_preto and not preto_ok:
        print(f"\n   🎨 Versão PRETA ({svg_preto.name})...")
        try:
            png = processar_svg_para_municipio(
                svg_preto, bounds_mun, bounds_estado, nome_arquivo, "preto", nome_oficial, pasta_uf
            )
            if png:
                resultados.append({"cor": "preto", "png": png})
        except Exception as e:
            print(f"      ❌ Erro: {e}")
            import traceback; traceback.print_exc()

    if svg_branco and not branco_ok:
        print(f"\n   🎨 Versão BRANCA ({svg_branco.name})...")
        try:
            png = processar_svg_para_municipio(
                svg_branco, bounds_mun, bounds_estado, nome_arquivo, "branco", nome_oficial, pasta_uf
            )
            if png:
                resultados.append({"cor": "branco", "png": png})
        except Exception as e:
            print(f"      ❌ Erro: {e}")
            import traceback; traceback.print_exc()

    return {"municipio": nome_oficial, "codigo": codigo, "uf": uf, "arquivos": resultados}


# ─── Leitura do CSV e main ────────────────────────────────────────────────────

def ler_cidades_pendentes(filtro_uf=None):
    """Lê cidades_pendentes.csv e retorna lista de (cidade, uf)."""
    cidades = []
    try:
        with open(ARQUIVO_PENDENTES, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cidade = row['cidade'].strip()
                uf = row['uf'].strip().strip('"').upper()
                if not cidade or not uf:
                    continue
                if filtro_uf and uf != filtro_uf.upper():
                    continue
                cidades.append((cidade, uf))
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {ARQUIVO_PENDENTES}")
    except Exception as e:
        print(f"❌ Erro ao ler CSV: {e}")
    return cidades


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Processar cidades pendentes (cidades_pendentes.csv)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Processar todas as cidades pendentes
  python processar_pendentes.py

  # Processar apenas Paraná
  python processar_pendentes.py --uf PR

  # Processar batch: cidades 50 a 100
  python processar_pendentes.py --inicio 50 --fim 100

  # Processar uma única cidade
  python processar_pendentes.py --cidade "Toledo,PR"
        """,
    )
    parser.add_argument("--uf", help="Filtrar por estado (ex: PR, SC, RS)")
    parser.add_argument("--inicio", type=int, default=0, help="Índice inicial (default: 0)")
    parser.add_argument("--fim", type=int, default=None, help="Índice final exclusivo (default: fim)")
    parser.add_argument("--cidade", help="Processar apenas esta cidade (ex: 'Toledo,PR')")
    parser.add_argument("--forcar", action="store_true", help="Reprocessar mesmo que já exista")
    args = parser.parse_args()

    print("=" * 60)
    print("   PROCESSAR CIDADES PENDENTES")
    print("=" * 60)
    print(f"   SVGs: {PASTA_SVG}")
    print(f"   Saída: {PASTA_SAIDA}")

    if args.cidade:
        if ',' not in args.cidade:
            print("❌ Use o formato 'Cidade,UF'")
            sys.exit(1)
        cidade, uf = args.cidade.rsplit(',', 1)
        processar_municipio(cidade.strip(), uf.strip().upper())
        return

    cidades = ler_cidades_pendentes(filtro_uf=args.uf)
    total_csv = len(cidades)
    cidades = cidades[args.inicio:args.fim]

    print(f"\n📋 {total_csv} cidades no CSV", end="")
    if args.uf:
        print(f" (filtro: {args.uf})", end="")
    print(f"\n   Processando {len(cidades)} cidades"
          f" (índice {args.inicio}–{args.fim or total_csv})\n")

    if args.forcar:
        # Limpa cache de SVG para forçar reprocessamento
        _cache_bounds_svg.clear()
        _cache_paths_svg.clear()

    sucessos = erros = pulados = 0

    for i, (cidade, uf) in enumerate(cidades):
        print(f"\n[{i + 1 + args.inicio}/{total_csv}]", end=" ")
        try:
            resultado = processar_municipio(cidade, uf)
            if resultado is None:
                erros += 1
            elif resultado.get('status') == 'ja_existia':
                pulados += 1
            else:
                gerados = len(resultado.get('arquivos', []))
                if gerados > 0:
                    sucessos += 1
                else:
                    erros += 1
        except Exception as e:
            print(f"   ❌ Erro inesperado: {e}")
            erros += 1

    print(f"\n{'='*60}")
    print(f"✅ Concluído: {sucessos} gerados  |  {pulados} pulados  |  {erros} erros")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
