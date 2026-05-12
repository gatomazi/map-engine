#!/usr/bin/env python3
"""
Pintar Municípios em SVG de Estados
------------------------------------
Este programa:
1. Recebe uma lista de municípios (ex: "Toledo,PR")
2. Carrega o SVG original do estado da pasta svg_estados
3. Identifica e pinta o município na localização correta
4. Gera PNGs com fundo transparente preservando o stroke original (0.7mm)
"""

import math
import os
import re
import requests
import sys
from pathlib import Path

import cairosvg
from lxml import etree

_ROOT = Path(__file__).resolve().parent.parent.parent
_ASSETS = Path(os.environ.get("ASSETS_DIR", str(_ROOT / "assets")))
PASTA_SVG = _ASSETS / "svg_estados"
_OUTPUT = Path(os.environ.get("OUTPUT_DIR", str(_ROOT / ".data" / "output")))
PASTA_SAIDA = _OUTPUT / "pintar_municipio"
PASTA_SAIDA.mkdir(parents=True, exist_ok=True)

# Namespaces SVG
NSMAP = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
}


def normalizar_nome(nome):
    """Normaliza o nome para comparação (sem acentos, minúsculas)."""
    import unicodedata
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.lower().strip().replace('-', ' ')


def buscar_svg_estado(uf, variante):
    """
    Busca o arquivo SVG do estado de forma case-insensitive.
    
    Args:
        uf: Sigla do estado (ex: 'GO', 'go', 'Go')
        variante: 'preto' ou 'branco'
    
    Returns:
        Path do arquivo encontrado ou None se não existir
    """
    # Padrão esperado: UF_variante.svg (ex: GO_preto.svg, go_branco.svg)
    nome_esperado = f"{uf.lower()}_{variante.lower()}.svg"
    
    if not PASTA_SVG.exists():
        return None
    
    # Lista todos os arquivos e busca match case-insensitive
    for arquivo in PASTA_SVG.iterdir():
        if arquivo.is_file() and arquivo.name.lower() == nome_esperado:
            return arquivo
    
    return None


def buscar_codigo_ibge(uf, cidade):
    """Busca o código IBGE do município."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            municipios = response.json()
            cidade_norm = normalizar_nome(cidade)
            
            for m in municipios:
                if normalizar_nome(m["nome"]) == cidade_norm:
                    return m["id"], m["nome"]
    except Exception as e:
        print(f"   ⚠️ Erro ao buscar código: {e}")
    
    return None, None


def baixar_geojson_municipio(codigo):
    """Baixa o GeoJSON do município."""
    url = f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}?formato=application/vnd.geo+json"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"   ⚠️ Erro ao baixar GeoJSON: {e}")
    
    return None


def extrair_todas_coordenadas(geojson):
    """Extrai todas as coordenadas de um GeoJSON."""
    coords = []
    
    def extrair(obj):
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                coords.append((obj[0], obj[1]))
            else:
                for item in obj:
                    extrair(item)
        elif isinstance(obj, dict):
            if "coordinates" in obj:
                extrair(obj["coordinates"])
            elif "geometry" in obj:
                extrair(obj["geometry"])
            elif "features" in obj:
                for f in obj["features"]:
                    extrair(f)
    
    extrair(geojson)
    return coords


def calcular_centroide(coords):
    """Calcula o centróide de uma lista de coordenadas."""
    if not coords:
        return None
    
    sum_lon = sum(c[0] for c in coords)
    sum_lat = sum(c[1] for c in coords)
    n = len(coords)
    
    return (sum_lon / n, sum_lat / n)


def calcular_bounds(coords):
    """Calcula os limites (bounding box) de uma lista de coordenadas."""
    if not coords:
        return None
    
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    
    return {
        "min_lon": min(lons),
        "max_lon": max(lons),
        "min_lat": min(lats),
        "max_lat": max(lats),
        "center_lon": (min(lons) + max(lons)) / 2,
        "center_lat": (min(lats) + max(lats)) / 2
    }


def baixar_bounds_estado(uf):
    """Baixa os bounds do estado para calcular transformação."""
    url_estados = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
    
    try:
        response = requests.get(url_estados, timeout=30)
        if response.status_code == 200:
            estados = response.json()
            codigo_uf = None
            for e in estados:
                if e["sigla"].upper() == uf.upper():
                    codigo_uf = e["id"]
                    break
            
            if codigo_uf:
                url = f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo_uf}?formato=application/vnd.geo+json"
                response = requests.get(url, timeout=60)
                if response.status_code == 200:
                    geojson = response.json()
                    coords = extrair_todas_coordenadas(geojson)
                    return calcular_bounds(coords)
    except Exception as e:
        print(f"   ⚠️ Erro ao baixar bounds do estado: {e}")
    
    return None


def parse_svg_path(d):
    """Extrai pontos de um path SVG."""
    pontos = []
    
    # Remove comandos de path e extrai números
    # Formato esperado: "m x,y l dx,dy ..." ou "M x,y L x,y ..."
    d = d.replace(',', ' ')
    partes = re.split(r'([MmLlHhVvCcSsQqTtAaZz])', d)
    
    x, y = 0, 0
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
        
        numeros = re.findall(r'-?[\d.]+(?:[eE][+-]?\d+)?', parte)
        
        j = 0
        while j < len(numeros):
            if comando in 'Mm':
                dx, dy = float(numeros[j]), float(numeros[j+1])
                if comando == 'm':
                    x, y = x + dx, y + dy
                else:
                    x, y = dx, dy
                pontos.append((x, y))
                j += 2
                comando = 'l' if comando == 'm' else 'L'
            elif comando in 'Ll':
                dx, dy = float(numeros[j]), float(numeros[j+1])
                if comando == 'l':
                    x, y = x + dx, y + dy
                else:
                    x, y = dx, dy
                pontos.append((x, y))
                j += 2
            elif comando in 'Hh':
                dx = float(numeros[j])
                if comando == 'h':
                    x = x + dx
                else:
                    x = dx
                pontos.append((x, y))
                j += 1
            elif comando in 'Vv':
                dy = float(numeros[j])
                if comando == 'v':
                    y = y + dy
                else:
                    y = dy
                pontos.append((x, y))
                j += 1
            elif comando in 'Cc':
                # Bezier cúbico: 6 números
                if j + 5 < len(numeros):
                    if comando == 'c':
                        x, y = x + float(numeros[j+4]), y + float(numeros[j+5])
                    else:
                        x, y = float(numeros[j+4]), float(numeros[j+5])
                    pontos.append((x, y))
                j += 6
            elif comando in 'Ss':
                if j + 3 < len(numeros):
                    if comando == 's':
                        x, y = x + float(numeros[j+2]), y + float(numeros[j+3])
                    else:
                        x, y = float(numeros[j+2]), float(numeros[j+3])
                    pontos.append((x, y))
                j += 4
            elif comando in 'Qq':
                if j + 3 < len(numeros):
                    if comando == 'q':
                        x, y = x + float(numeros[j+2]), y + float(numeros[j+3])
                    else:
                        x, y = float(numeros[j+2]), float(numeros[j+3])
                    pontos.append((x, y))
                j += 4
            elif comando in 'Tt':
                if j + 1 < len(numeros):
                    if comando == 't':
                        x, y = x + float(numeros[j]), y + float(numeros[j+1])
                    else:
                        x, y = float(numeros[j]), float(numeros[j+1])
                    pontos.append((x, y))
                j += 2
            elif comando in 'Aa':
                if j + 6 < len(numeros):
                    if comando == 'a':
                        x, y = x + float(numeros[j+5]), y + float(numeros[j+6])
                    else:
                        x, y = float(numeros[j+5]), float(numeros[j+6])
                    pontos.append((x, y))
                j += 7
            elif comando in 'Zz':
                break
            else:
                j += 1
        
        i += 1
    
    return pontos


def calcular_centroide_path(pontos):
    """Calcula o centróide de um path SVG."""
    if not pontos:
        return None
    
    sum_x = sum(p[0] for p in pontos)
    sum_y = sum(p[1] for p in pontos)
    n = len(pontos)
    
    return (sum_x / n, sum_y / n)


def calcular_bounds_path(pontos):
    """Calcula bounding box de um path SVG."""
    if not pontos:
        return None
    
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    
    return {
        'min_x': min(xs),
        'max_x': max(xs),
        'min_y': min(ys),
        'max_y': max(ys),
        'width': max(xs) - min(xs),
        'height': max(ys) - min(ys)
    }


def calcular_area_aproximada(pontos):
    """Calcula área aproximada de um polígono usando a fórmula de Shoelace."""
    if not pontos or len(pontos) < 3:
        return 0
    
    n = len(pontos)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += pontos[i][0] * pontos[j][1]
        area -= pontos[j][0] * pontos[i][1]
    
    return abs(area) / 2


def ponto_em_poligono(x, y, pontos):
    """Verifica se um ponto está dentro de um polígono (ray casting)."""
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
    """Calcula distância euclidiana entre dois pontos."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def encontrar_path_por_label(svg_tree, nome_municipio):
    """
    Encontra o path no SVG pelo label (inkscape:label).
    """
    nome_norm      = normalizar_nome(nome_municipio)
    nome_norm_nsp  = nome_norm.replace(' ', '')

    # Busca todos os paths no SVG
    paths = svg_tree.xpath('//*[local-name()="path"]')

    for path in paths:
        # Verifica inkscape:label
        label = path.get('{http://www.inkscape.org/namespaces/inkscape}label')
        if label:
            label_norm = normalizar_nome(label)
            if label_norm == nome_norm or label_norm.replace(' ', '') == nome_norm_nsp:
                d = path.get('d')
                if d:
                    pontos = parse_svg_path(d)
                    return path, pontos

    return None, None


def extrair_transform_do_layer(svg_tree):
    """Extrai a transformação translate do layer principal."""
    # Busca o layer1 que contém os municípios
    layers = svg_tree.xpath('//*[@id="layer1"]')
    
    for layer in layers:
        transform = layer.get('transform', '')
        # Procura por translate(x,y)
        match = re.search(r'translate\(([-\d.]+)\s*,?\s*([-\d.]+)\)', transform)
        if match:
            return (float(match.group(1)), float(match.group(2)))
    
    return (0, 0)


def calcular_offset_calibracao(svg_tree, bounds_estado, viewbox, transform, centroide_alvo=None):
    """
    Calcula o offset de calibração usando um município de referência com label conhecido.
    Se centroide_alvo for fornecido, usa a referência mais próxima.
    """
    # Referências conhecidas (centróide IBGE) - coordenadas atualizadas
    referencias = {
        'floripa': {'lon': -48.4707, 'lat': -27.5582},
        'florianopolis': {'lon': -48.4707, 'lat': -27.5582},
        'joinville': {'lon': -48.9629, 'lat': -26.2633},
        'blumenau': {'lon': -49.1068, 'lat': -26.8728},
        'luzerna': {'lon': -51.5141, 'lat': -27.0951},
        'salto veloso': {'lon': -50.3417, 'lat': -27.2917},
        'lajes': {'lon': -50.3478, 'lat': -28.0013},
        'criciuma': {'lon': -49.3606, 'lat': -28.7445},
        'indaial': {'lon': -49.2266, 'lat': -26.9975},
        'ibirama': {'lon': -49.5288, 'lat': -27.0140},
        'vargem': {'lon': -50.9524, 'lat': -27.4690},
        'rio negrinho': {'lon': -49.3898, 'lat': -26.6304},
        'bela vista do toldo': {'lon': -50.4882, 'lat': -26.4360},
        'rancho queimado': {'lon': -49.3393, 'lat': -27.2573},
        'palhoca': {'lon': -48.6607, 'lat': -27.7619},
        'bc': {'lon': -48.6264, 'lat': -27.0076},
        'jaragua do sul': {'lon': -49.1569, 'lat': -26.4324},
        'sao francisco do sul': {'lon': -48.6323, 'lat': -26.2913},
    }
    
    paths = svg_tree.xpath('//*[local-name()="path"]')
    
    # Primeiro, coleta todas as referências disponíveis no SVG
    refs_disponiveis = []
    for path in paths:
        label = path.get('{http://www.inkscape.org/namespaces/inkscape}label', '').lower()
        if label in referencias:
            ref = referencias[label]
            d = path.get('d')
            if not d:
                continue
            
            pontos = parse_svg_path(d)
            if len(pontos) < 3:
                continue
            
            # Centro do path no SVG
            xs = [p[0] for p in pontos]
            ys = [p[1] for p in pontos]
            svg_center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
            
            refs_disponiveis.append({
                'label': label,
                'ref': ref,
                'svg_center': svg_center
            })
    
    if not refs_disponiveis:
        return (0, 0)
    
    # Se tem centroide_alvo, encontra a referência mais próxima
    lon_range = bounds_estado['max_lon'] - bounds_estado['min_lon']
    lat_range = bounds_estado['max_lat'] - bounds_estado['min_lat']
    margem_x = viewbox['width'] * 0.05
    margem_y = viewbox['height'] * 0.05
    area_util_w = viewbox['width'] - 2 * margem_x
    area_util_h = viewbox['height'] - 2 * margem_y
    
    if centroide_alvo:
        # Calcula posição SVG estimada do alvo (sem offset)
        alvo_x = viewbox['x'] + margem_x + ((centroide_alvo[0] - bounds_estado['min_lon']) / lon_range) * area_util_w - transform[0]
        alvo_y = viewbox['y'] + margem_y + ((bounds_estado['max_lat'] - centroide_alvo[1]) / lat_range) * area_util_h - transform[1]
        
        # Encontra a referência mais próxima
        melhor_ref = None
        menor_dist = float('inf')
        for ref_info in refs_disponiveis:
            dist = ((ref_info['svg_center'][0] - alvo_x)**2 + (ref_info['svg_center'][1] - alvo_y)**2)**0.5
            if dist < menor_dist:
                menor_dist = dist
                melhor_ref = ref_info
    else:
        # Usa floripa como padrão
        melhor_ref = next((r for r in refs_disponiveis if r['label'] in ['floripa', 'florianopolis']), refs_disponiveis[0])
    
    if not melhor_ref:
        return (0, 0)
    
    # Calcula offset usando a referência escolhida
    ref = melhor_ref['ref']
    svg_center = melhor_ref['svg_center']
    
    calc_x = viewbox['x'] + margem_x + ((ref['lon'] - bounds_estado['min_lon']) / lon_range) * area_util_w
    calc_y = viewbox['y'] + margem_y + ((bounds_estado['max_lat'] - ref['lat']) / lat_range) * area_util_h
    
    # Aplicar transform
    calc_x -= transform[0]
    calc_y -= transform[1]
    
    # Offset = diferença entre calculado e real
    offset = (calc_x - svg_center[0], calc_y - svg_center[1])
    print(f"      Calibração usando '{melhor_ref['label']}': offset=({offset[0]:.0f}, {offset[1]:.0f})")
    return offset


def calcular_extent_paths(svg_tree):
    """Calcula a extensão real (bbox) de todos os paths no SVG."""
    paths = svg_tree.xpath('//*[local-name()="path"]')
    all_x, all_y = [], []
    for p in paths:
        d = p.get('d', '')
        pts = parse_svg_path(d)
        if len(pts) < 3:
            continue
        all_x += [pt[0] for pt in pts]
        all_y += [pt[1] for pt in pts]
    if not all_x:
        return None
    return {
        'min_x': min(all_x), 'max_x': max(all_x),
        'min_y': min(all_y), 'max_y': max(all_y),
        'width': max(all_x) - min(all_x),
        'height': max(all_y) - min(all_y),
    }


def converter_bounds_geo_para_svg(bounds_municipio, bounds_estado, viewbox, transform=(0, 0), offset=(0, 0), svg_extent=None):
    """
    Converte os bounds geográficos do município para bounds SVG.
    Considera a transformação do layer e o offset de calibração.
    Se svg_extent for fornecido, usa a extensão real dos paths em vez da margem estimada de 5%.
    """
    lon_range = bounds_estado['max_lon'] - bounds_estado['min_lon']
    lat_range = bounds_estado['max_lat'] - bounds_estado['min_lat']

    if lon_range == 0 or lat_range == 0:
        return None

    if svg_extent:
        # Usa extensão real dos paths — mais preciso para SVGs sem inkscape:label
        area_util_w = svg_extent['width']
        area_util_h = svg_extent['height']
        base_x = svg_extent['min_x']
        base_y = svg_extent['min_y']
    else:
        # Margem estimada do SVG (5% — funciona para estados com calibração por label)
        margem_x = viewbox['width'] * 0.05
        margem_y = viewbox['height'] * 0.05
        area_util_w = viewbox['width'] - 2 * margem_x
        area_util_h = viewbox['height'] - 2 * margem_y
        base_x = viewbox['x'] + margem_x
        base_y = viewbox['y'] + margem_y

    # Converte cada canto do bounding box
    min_x_svg = base_x + ((bounds_municipio['min_lon'] - bounds_estado['min_lon']) / lon_range) * area_util_w
    max_x_svg = base_x + ((bounds_municipio['max_lon'] - bounds_estado['min_lon']) / lon_range) * area_util_w

    # Latitude invertida (Y cresce para baixo)
    min_y_svg = base_y + ((bounds_estado['max_lat'] - bounds_municipio['max_lat']) / lat_range) * area_util_h
    max_y_svg = base_y + ((bounds_estado['max_lat'] - bounds_municipio['min_lat']) / lat_range) * area_util_h

    # Aplica transformação inversa do layer
    min_x_svg -= transform[0]
    max_x_svg -= transform[0]
    min_y_svg -= transform[1]
    max_y_svg -= transform[1]

    # Aplica offset de calibração
    min_x_svg -= offset[0]
    max_x_svg -= offset[0]
    min_y_svg -= offset[1]
    max_y_svg -= offset[1]

    return {
        'min_x': min_x_svg,
        'max_x': max_x_svg,
        'min_y': min_y_svg,
        'max_y': max_y_svg,
        'width': max_x_svg - min_x_svg,
        'height': max_y_svg - min_y_svg,
        'center_x': (min_x_svg + max_x_svg) / 2,
        'center_y': (min_y_svg + max_y_svg) / 2
    }


def calcular_iou(bounds1, bounds2):
    """
    Calcula Intersection over Union entre dois bounding boxes.
    Retorna valor entre 0 (sem sobreposição) e 1 (idênticos).
    """
    # Coordenadas da interseção
    inter_min_x = max(bounds1['min_x'], bounds2['min_x'])
    inter_max_x = min(bounds1['max_x'], bounds2['max_x'])
    inter_min_y = max(bounds1['min_y'], bounds2['min_y'])
    inter_max_y = min(bounds1['max_y'], bounds2['max_y'])
    
    # Área da interseção
    inter_width = max(0, inter_max_x - inter_min_x)
    inter_height = max(0, inter_max_y - inter_min_y)
    inter_area = inter_width * inter_height
    
    # Áreas individuais
    area1 = bounds1['width'] * bounds1['height']
    area2 = bounds2['width'] * bounds2['height']
    
    # União
    union_area = area1 + area2 - inter_area
    
    if union_area == 0:
        return 0
    
    return inter_area / union_area


def encontrar_path_por_bounds(svg_tree, bounds_municipio_svg, viewbox=None):
    """
    Encontra o path no SVG comparando os bounds do município (do IBGE) com os paths do SVG.
    Usa um score combinado de IoU, distância e similaridade de tamanho.
    """
    # Busca todos os paths no SVG
    paths = svg_tree.xpath('//*[local-name()="path"]')
    
    # Calcula área e tamanho esperados do município
    area_esperada = bounds_municipio_svg['width'] * bounds_municipio_svg['height']
    
    candidatos = []
    
    for path in paths:
        d = path.get('d')
        if not d:
            continue
        
        pontos = parse_svg_path(d)
        if len(pontos) < 3:
            continue
        
        bounds = calcular_bounds_path(pontos)
        if not bounds:
            continue
        
        # Filtra paths muito diferentes em tamanho (mais de 5x maior ou menor)
        area_path = bounds['width'] * bounds['height']
        if area_path > area_esperada * 5 or area_path < area_esperada * 0.2:
            continue
        
        # Calcula IoU
        bounds_dict = {
            'min_x': bounds['min_x'],
            'max_x': bounds['max_x'],
            'min_y': bounds['min_y'],
            'max_y': bounds['max_y'],
            'width': bounds['width'],
            'height': bounds['height']
        }
        iou = calcular_iou(bounds_municipio_svg, bounds_dict)
        
        # Calcula distância entre centróides
        centroide = calcular_centroide_path(pontos)
        dist = distancia((bounds_municipio_svg['center_x'], bounds_municipio_svg['center_y']), centroide) if centroide else float('inf')
        
        # Calcula similaridade de tamanho (0 a 1, maior é melhor)
        w_ratio = min(bounds['width'], bounds_municipio_svg['width']) / max(bounds['width'], bounds_municipio_svg['width'])
        h_ratio = min(bounds['height'], bounds_municipio_svg['height']) / max(bounds['height'], bounds_municipio_svg['height'])
        size_similarity = (w_ratio + h_ratio) / 2
        
        # Score combinado: prioriza IoU, mas considera tamanho e distância
        # Score alto é melhor
        score = (iou * 0.4) + (size_similarity * 0.4) + (1 / (1 + dist/100) * 0.2)
        
        candidatos.append({
            'path': path,
            'pontos': pontos,
            'bounds': bounds_dict,
            'iou': iou,
            'distancia': dist,
            'area': area_path,
            'size_sim': size_similarity,
            'score': score
        })
    
    if not candidatos:
        return None, None
    
    # Ordena por score combinado (maior é melhor)
    candidatos.sort(key=lambda c: -c['score'])
    
    melhor = candidatos[0]
    print(f"      Melhor match: score={melhor['score']:.4f}, IoU={melhor['iou']:.4f}, size_sim={melhor['size_sim']:.2f}, dist={melhor['distancia']:.2f}")
    
    return melhor['path'], melhor['pontos']


def encontrar_path_municipio(svg_tree, coord_municipio_svg, nome_municipio=None, viewbox=None, bounds_municipio_svg=None):
    """
    Encontra o path no SVG que representa o município.
    Estratégias em ordem de prioridade:
    1. Pelo label (inkscape:label)
    2. Pelos bounds do município (comparando com GeoJSON do IBGE)
    3. Pelo centróide/ponto dentro do polígono
    """
    # 1. Tenta encontrar pelo label (mais preciso)
    if nome_municipio:
        path, pontos = encontrar_path_por_label(svg_tree, nome_municipio)
        if path is not None:
            print(f"      ✓ Encontrado pelo label")
            return path, pontos
    
    # 2. Tenta encontrar pelos bounds (usando GeoJSON do IBGE)
    if bounds_municipio_svg:
        path, pontos = encontrar_path_por_bounds(svg_tree, bounds_municipio_svg, viewbox)
        if path is not None:
            return path, pontos
    
    # 3. Fallback: busca por coordenadas/centróide
    print(f"      ⚠️ Usando fallback por coordenadas")
    paths = svg_tree.xpath('//*[local-name()="path"]')
    
    candidatos = []
    
    for path in paths:
        d = path.get('d')
        if not d:
            continue
        
        pontos = parse_svg_path(d)
        if len(pontos) < 3:
            continue
        
        area = calcular_area_aproximada(pontos)
        bounds = calcular_bounds_path(pontos)
        
        # Filtra paths muito grandes
        if bounds and viewbox:
            if bounds['width'] > viewbox['width'] * 0.3 or bounds['height'] > viewbox['height'] * 0.3:
                continue
        
        if ponto_em_poligono(coord_municipio_svg[0], coord_municipio_svg[1], pontos):
            candidatos.append({
                'path': path,
                'pontos': pontos,
                'area': area,
                'distancia': 0,
                'dentro': True
            })
        else:
            centroide = calcular_centroide_path(pontos)
            if centroide:
                dist = distancia(coord_municipio_svg, centroide)
                candidatos.append({
                    'path': path,
                    'pontos': pontos,
                    'area': area,
                    'distancia': dist,
                    'dentro': False
                })
    
    if not candidatos:
        return None, None
    
    dentro = [c for c in candidatos if c['dentro']]
    if dentro:
        dentro.sort(key=lambda c: c['area'])
        return dentro[0]['path'], dentro[0]['pontos']
    
    candidatos.sort(key=lambda c: c['distancia'])
    return candidatos[0]['path'], candidatos[0]['pontos']


def geojson_para_svg_path_d(geojson, bounds_estado, viewbox, offset):
    """
    Projeta o polígono IBGE (GeoJSON) para string de path SVG usando a mesma
    projeção linear de transformar_geo_para_svg com o offset de calibração.
    Suporta Polygon e MultiPolygon.
    """
    aneis = []
    def coletar(obj):
        if isinstance(obj, dict):
            t = obj.get('type')
            c = obj.get('coordinates')
            if t == 'Polygon' and c:
                aneis.extend(c)
            elif t == 'MultiPolygon' and c:
                for poly in c:
                    aneis.extend(poly)
            else:
                for v in obj.values(): coletar(v)
        elif isinstance(obj, list):
            for i in obj: coletar(i)
    coletar(geojson)

    parts = []
    for anel in aneis:
        pts = []
        for coord in anel:
            lon, lat = coord[0], coord[1]
            p = transformar_geo_para_svg(lon, lat, bounds_estado, viewbox)
            if p:
                pts.append((p[0] - offset[0], p[1] - offset[1]))
        if len(pts) < 3:
            continue
        parts.append(f"M {pts[0][0]:.2f} {pts[0][1]:.2f}")
        for x, y in pts[1:]:
            parts.append(f"L {x:.2f} {y:.2f}")
        parts.append("Z")

    return " ".join(parts) if parts else None


def extrair_viewbox(svg_tree):
    """Extrai viewBox do SVG."""
    root = svg_tree.getroot()
    viewbox = root.get('viewBox')
    
    if viewbox:
        partes = viewbox.split()
        if len(partes) >= 4:
            return {
                'x': float(partes[0]),
                'y': float(partes[1]),
                'width': float(partes[2]),
                'height': float(partes[3])
            }
    
    # Fallback para width/height
    width = root.get('width', '800')
    height = root.get('height', '600')
    
    # Remove 'mm', 'px', etc.
    width = float(re.sub(r'[^\d.]', '', width) or 800)
    height = float(re.sub(r'[^\d.]', '', height) or 600)
    
    return {'x': 0, 'y': 0, 'width': width, 'height': height}


def transformar_geo_para_svg(lon, lat, bounds_estado, viewbox):
    """
    Transforma coordenadas geográficas para coordenadas SVG.
    """
    # Range das coordenadas geográficas
    lon_range = bounds_estado['max_lon'] - bounds_estado['min_lon']
    lat_range = bounds_estado['max_lat'] - bounds_estado['min_lat']
    
    if lon_range == 0 or lat_range == 0:
        return None
    
    # Normaliza a longitude (0 a 1)
    norm_lon = (lon - bounds_estado['min_lon']) / lon_range
    
    # Normaliza a latitude (invertido porque Y cresce para baixo no SVG)
    norm_lat = (bounds_estado['max_lat'] - lat) / lat_range
    
    # Converte para coordenadas SVG
    # Usa uma margem estimada (geralmente os SVGs têm margem)
    margem_x = viewbox['width'] * 0.05
    margem_y = viewbox['height'] * 0.05
    
    svg_x = viewbox['x'] + margem_x + norm_lon * (viewbox['width'] - 2 * margem_x)
    svg_y = viewbox['y'] + margem_y + norm_lat * (viewbox['height'] - 2 * margem_y)
    
    return (svg_x, svg_y)


def extrair_cor_do_svg(svg_tree):
    """Extrai a cor de stroke dos paths do SVG."""
    paths = svg_tree.xpath('//*[local-name()="path"]')
    
    for path in paths:
        style = path.get('style', '')
        
        # Busca stroke no style
        match = re.search(r'stroke:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)', style)
        if match:
            return match.group(1)
        
        # Busca stroke como atributo
        stroke = path.get('stroke')
        if stroke:
            return stroke
    
    return '#000000'  # Default preto


def processar_municipio(cidade, uf, pasta_uf_dest=None):
    """Processa um município e gera os PNGs usando os SVGs originais.

    pasta_uf_dest: se informado, grava os PNGs nessa pasta (ex.: temp dir da API).
    Caso contrário, usa OUTPUT_DIR/pintar_municipio/{UF}/.
    """
    print(f"\n{'='*60}")
    print(f"📍 Processando: {cidade}/{uf}")
    print(f"{'='*60}")

    # 0. Registra solicitação se a cidade for pendente (ainda não gerada)
    try:
        from rastrear_solicitacoes import verificar_cidade
        resultado = verificar_cidade(cidade, uf, registrar=True)
        if resultado['status'] == 'disponivel':
            print(f"   ℹ️  Cidade já gerada anteriormente:")
            for f in resultado['arquivos']:
                print(f"      {f}")
    except ImportError:
        pass

    # 1. Verifica se existem os SVGs do estado (case-insensitive)
    svg_preto_path = buscar_svg_estado(uf, "preto")
    svg_branco_path = buscar_svg_estado(uf, "branco")
    
    if not svg_preto_path and not svg_branco_path:
        print(f"   ❌ SVGs do estado {uf} não encontrados em {PASTA_SVG}")
        print(f"      Esperado: {uf}_preto.svg e/ou {uf}_branco.svg (case-insensitive)")
        return None
    
    # 2. Busca código IBGE
    print(f"\n   🔍 Buscando código IBGE...")
    codigo, nome_oficial = buscar_codigo_ibge(uf, cidade)
    
    if not codigo:
        print(f"   ❌ Município '{cidade}' não encontrado em {uf}")
        return None
    
    print(f"   ✅ Código: {codigo} - {nome_oficial}")
    
    # 3. Baixa GeoJSON do município
    print(f"\n   📥 Baixando limites do município...")
    geojson_municipio = baixar_geojson_municipio(codigo)
    
    if not geojson_municipio:
        print(f"   ❌ Não foi possível baixar GeoJSON do município")
        return None
    
    # Calcula centróide do município
    coords_municipio = extrair_todas_coordenadas(geojson_municipio)
    centroide_municipio = calcular_centroide(coords_municipio)
    bounds_municipio = calcular_bounds(coords_municipio)
    
    if not centroide_municipio:
        print(f"   ❌ Não foi possível calcular centróide do município")
        return None
    
    print(f"   ✅ Centróide: {centroide_municipio[0]:.4f}, {centroide_municipio[1]:.4f}")
    
    # 4. Baixa bounds do estado
    print(f"\n   📥 Obtendo limites do estado {uf}...")
    bounds_estado = baixar_bounds_estado(uf)
    
    if not bounds_estado:
        print(f"   ❌ Não foi possível obter limites do estado")
        return None
    
    print(f"   ✅ Bounds estado: lon({bounds_estado['min_lon']:.2f}, {bounds_estado['max_lon']:.2f}), lat({bounds_estado['min_lat']:.2f}, {bounds_estado['max_lat']:.2f})")
    
    resultados = []
    nome_arquivo = normalizar_nome(nome_oficial).replace(' ', '_')
    if pasta_uf_dest is not None:
        pasta_uf = Path(pasta_uf_dest)
        pasta_uf.mkdir(parents=True, exist_ok=True)
    else:
        pasta_uf = PASTA_SAIDA / uf.upper()

    # 5. Processa versão preta
    if svg_preto_path:
        print(f"\n   🎨 Processando versão PRETA ({svg_preto_path.name})...")
        resultado = processar_svg(
            svg_preto_path,
            centroide_municipio,
            bounds_estado,
            bounds_municipio,
            codigo,
            nome_arquivo,
            "preto",
            nome_oficial,
            output_dir=pasta_uf,
            geojson_municipio=geojson_municipio,
        )
        if resultado:
            resultados.append(resultado)

    # 6. Processa versão branca
    if svg_branco_path:
        print(f"\n   🎨 Processando versão BRANCA ({svg_branco_path.name})...")
        resultado = processar_svg(
            svg_branco_path,
            centroide_municipio,
            bounds_estado,
            bounds_municipio,
            codigo,
            nome_arquivo,
            "branco",
            nome_oficial,
            output_dir=pasta_uf,
            geojson_municipio=geojson_municipio,
        )
        if resultado:
            resultados.append(resultado)
    
    return {
        "municipio": nome_oficial,
        "codigo": codigo,
        "uf": uf,
        "arquivos": resultados
    }


def processar_svg(svg_path, centroide_geo, bounds_estado, bounds_municipio, codigo, nome_arquivo, cor, nome_oficial=None, output_dir=None, geojson_municipio=None):
    """Processa um SVG e gera o PNG com o município pintado."""
    try:
        # Carrega o SVG
        parser = etree.XMLParser(remove_blank_text=True)
        svg_tree = etree.parse(str(svg_path), parser)
        root = svg_tree.getroot()
        
        # Obtém viewBox
        viewbox = extrair_viewbox(svg_tree)
        print(f"      ViewBox: {viewbox}")
        
        # Extrai transformação do layer
        transform = extrair_transform_do_layer(svg_tree)
        print(f"      Transform: {transform}")
        
        # Calcula offset de calibração usando município de referência mais próximo
        offset = calcular_offset_calibracao(svg_tree, bounds_estado, viewbox, transform, centroide_geo)

        # Verifica se o SVG tem labels (estados Sul/CO) ou não (estados Norte sem labels)
        tem_labels = any(
            p.get('{http://www.inkscape.org/namespaces/inkscape}label')
            for p in svg_tree.xpath('//*[local-name()="path"]')
        )
        # Quando não há labels (offset=0,0), usa extensão real dos paths para projeção precisa
        svg_extent = None if tem_labels else calcular_extent_paths(svg_tree)
        if svg_extent:
            print(f"      SVG sem labels — usando extent real: x=[{svg_extent['min_x']:.0f},{svg_extent['max_x']:.0f}] y=[{svg_extent['min_y']:.0f},{svg_extent['max_y']:.0f}]")

        # Transforma coordenadas geográficas para SVG
        coord_svg = transformar_geo_para_svg(
            centroide_geo[0],
            centroide_geo[1],
            bounds_estado,
            viewbox
        )

        if not coord_svg:
            print(f"      ⚠️ Não foi possível transformar coordenadas")
            return None

        # Converte bounds do município para coordenadas SVG (com calibração)
        bounds_municipio_svg = converter_bounds_geo_para_svg(
            bounds_municipio,
            bounds_estado,
            viewbox,
            transform,
            offset,
            svg_extent=svg_extent
        )
        
        # Aplica transformação e offset às coordenadas do centróide
        coord_svg_ajustado = (
            coord_svg[0] - transform[0] - offset[0], 
            coord_svg[1] - transform[1] - offset[1]
        )
        
        print(f"      Coord SVG calibrada: ({coord_svg_ajustado[0]:.2f}, {coord_svg_ajustado[1]:.2f})")
        if bounds_municipio_svg:
            print(f"      Bounds SVG município: ({bounds_municipio_svg['min_x']:.0f},{bounds_municipio_svg['min_y']:.0f}) - ({bounds_municipio_svg['max_x']:.0f},{bounds_municipio_svg['max_y']:.0f})")
        
        # Extrai cor original do SVG (necessário para ambas as estratégias)
        cor_original = extrair_cor_do_svg(svg_tree)
        print(f"      Cor original: {cor_original}")

        # Tenta label match primeiro
        path_element = None
        pontos       = None
        if nome_oficial:
            path_element, pontos = encontrar_path_por_label(svg_tree, nome_oficial)
            if path_element is not None:
                print(f"      ✓ Encontrado pelo label")

        # Sem label: usa polígono IBGE projetado diretamente (mais preciso que bounds matching)
        if path_element is None and geojson_municipio is not None:
            path_d = geojson_para_svg_path_d(geojson_municipio, bounds_estado, viewbox, offset)
            if path_d:
                root = svg_tree.getroot()
                new_el = etree.SubElement(root, 'path')
                new_el.set('d', path_d)
                new_el.set('style', f'fill:{cor_original};fill-opacity:1;stroke:none')
                path_element = new_el
                print(f"      ✓ Usando polígono IBGE projetado")

        # Fallback final: bounds matching
        if path_element is None:
            path_element, pontos = encontrar_path_municipio(svg_tree, coord_svg_ajustado, nome_oficial, viewbox, bounds_municipio_svg)

        if path_element is None:
            print(f"      ⚠️ Path do município não encontrado")
            return None

        centroide_path = calcular_centroide_path(pontos) if pontos else None
        if centroide_path:
            print(f"      Centróide do path: ({centroide_path[0]:.2f}, {centroide_path[1]:.2f})")

        # Modifica o style do path para preencher (só se não foi criado pelo IBGE)
        if pontos is not None:
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
        
        # Salva o SVG modificado
        pasta_out = Path(output_dir) if output_dir else PASTA_SAIDA
        pasta_out.mkdir(parents=True, exist_ok=True)
        svg_saida = pasta_out / f"{nome_arquivo}_{cor}.svg"
        svg_tree.write(str(svg_saida), encoding='UTF-8', xml_declaration=True)
        print(f"      ✅ SVG: {svg_saida}")

        # Converte para PNG com fundo transparente
        png_saida = pasta_out / f"{nome_arquivo}_{cor}.png"
        
        # Lê o SVG como string para cairosvg
        with open(svg_saida, 'rb') as f:
            svg_content = f.read()
        
        # Converte para PNG - sem background_color = transparente
        cairosvg.svg2png(
            bytestring=svg_content,
            write_to=str(png_saida),
            dpi=300  # Alta resolução
        )
        
        print(f"      ✅ PNG: {png_saida}")
        
        # Remove o SVG temporário, mantém apenas o PNG
        if svg_saida.exists():
            svg_saida.unlink()
            print(f"      🗑️ SVG removido")
        
        return {"cor": cor, "png": str(png_saida)}
        
    except Exception as e:
        print(f"      ❌ Erro ao processar SVG: {e}")
        import traceback
        traceback.print_exc()
        return None


def carregar_municipios_arquivo(arquivo):
    """Carrega lista de municípios de um arquivo."""
    municipios = []
    
    try:
        with open(arquivo, 'r', encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                # Ignora linhas vazias e comentários
                if not linha or linha.startswith('#'):
                    continue
                municipios.append(linha)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {arquivo}")
    except Exception as e:
        print(f"❌ Erro ao ler arquivo: {e}")
    
    return municipios


def main():
    """Função principal."""
    import argparse
    
    # Arquivo padrão de municípios
    arquivo_padrao = Path(__file__).parent / "municipios.txt"
    
    parser = argparse.ArgumentParser(
        description="Pintar Municípios em SVG de Estados",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Exemplos:
  # Processar municípios do arquivo padrão (municipios.txt)
  python pintar_municipio.py
  
  # Processar municípios de outro arquivo
  python pintar_municipio.py -a minha_lista.txt
  
  # Processar municípios específicos
  python pintar_municipio.py "Toledo,PR" "Joinville,SC"

Arquivo de entrada ({arquivo_padrao}):
  - Um município por linha no formato: Cidade,UF
  - Linhas começando com # são comentários
  - Linhas em branco são ignoradas

Os SVGs do estado devem estar na pasta svg_estados/ no formato:
  UF_preto.svg  (ex: PR_preto.svg)
  UF_branco.svg (ex: PR_branco.svg)
        """
    )
    
    parser.add_argument("municipios", nargs="*", 
                        help="Municípios no formato 'Cidade,UF' (ex: 'Toledo,PR')")
    parser.add_argument("-a", "--arquivo", type=str, default=None,
                        help=f"Arquivo com lista de municípios (padrão: {arquivo_padrao})")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("       PINTAR MUNICÍPIOS EM SVG DE ESTADOS")
    print("=" * 60)
    print(f"\n📁 Pasta SVGs: {PASTA_SVG}")
    print(f"📁 Pasta Saída: {PASTA_SAIDA}")
    
    # Determina a lista de municípios
    if args.municipios:
        # Usa municípios passados como argumento
        lista_municipios = args.municipios
        print(f"\n📋 Processando {len(lista_municipios)} município(s) da linha de comando")
    else:
        # Carrega do arquivo
        arquivo = args.arquivo if args.arquivo else arquivo_padrao
        print(f"\n📄 Carregando municípios de: {arquivo}")
        lista_municipios = carregar_municipios_arquivo(arquivo)
        
        if not lista_municipios:
            print(f"\n⚠️ Nenhum município encontrado no arquivo.")
            print(f"   Edite o arquivo {arquivo} e adicione os municípios desejados.")
            print(f"   Formato: Cidade,UF (um por linha)")
            return []
        
        print(f"   📋 {len(lista_municipios)} município(s) encontrado(s)")
    
    resultados = []
    
    for item in lista_municipios:
        if ',' not in item:
            print(f"\n⚠️ Formato inválido: '{item}'. Use 'Cidade,UF'")
            continue
        
        partes = item.rsplit(',', 1)
        cidade = partes[0].strip()
        uf = partes[1].strip().upper()
        
        resultado = processar_municipio(cidade, uf)
        if resultado:
            resultados.append(resultado)
    
    print(f"\n{'='*60}")
    print(f"✅ PROCESSAMENTO CONCLUÍDO!")
    print(f"   Sucessos: {len(resultados)}/{len(lista_municipios)}")
    print(f"{'='*60}")
    
    return resultados


if __name__ == "__main__":
    main()
