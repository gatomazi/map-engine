#!/usr/bin/env python3
"""
Criar SVG de Contorno dos Estados
----------------------------------
Gera UF_contorno_branco.svg e UF_contorno_preto.svg em svg_estados/:
  - Um único path com o contorno externo do estado
  - Sem bordas municipais internas
  - Stroke mais grosso que o SVG de municípios
  - Mesmo espaço de coordenadas dos SVGs existentes

Usado na composição do estilo V1-d (bordas internas finas + contorno grosso).

Uso:
  python criar_contorno.py --uf PR
  python criar_contorno.py --uf PR SC RS GO MS
  python criar_contorno.py --todos
"""

import os
import sys
import requests
from pathlib import Path
from lxml import etree

def _default_assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "assets"


ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", str(_default_assets_dir())))
PASTA_SVG = ASSETS_DIR / "svg_estados"
PASTA_SVG.mkdir(parents=True, exist_ok=True)

CODIGOS_UF = {
    'AC': 12, 'AL': 27, 'AP': 16, 'AM': 13, 'BA': 29, 'CE': 23,
    'DF': 53, 'ES': 32, 'GO': 52, 'MA': 21, 'MT': 51, 'MS': 50,
    'MG': 31, 'PA': 15, 'PB': 25, 'PR': 41, 'PE': 26, 'PI': 22,
    'RJ': 33, 'RN': 24, 'RS': 43, 'RO': 11, 'RR': 14, 'SC': 42,
    'SP': 35, 'SE': 28, 'TO': 17,
}

# Stroke do contorno em unidades SVG (os SVGs de município usam ~8.27)
STROKE_CONTORNO = 12.0

COR_BRANCO = '#ffffff'
COR_PRETO  = '#2a2e22'


# ─── IBGE API ─────────────────────────────────────────────────────────────────

def baixar_geojson_contorno(codigo_uf, resolucao=4):
    """Baixa o polígono unificado do estado (sem divisões internas)."""
    url = (f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo_uf}"
           f"?formato=application/vnd.geo+json&resolucao={resolucao}")
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"   ⚠️  Erro ao baixar contorno GeoJSON: {e}")
    return None


def baixar_geo_bounds(codigo_uf):
    """Calcula os bounds geográficos do estado (resolução mínima = rápido)."""
    url = (f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{codigo_uf}"
           f"?formato=application/vnd.geo+json&qualidade=minima")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        coords = _extrair_coords(r.json())
    except Exception as e:
        print(f"   ⚠️  Erro ao baixar geo bounds: {e}")
        return None

    if not coords:
        return None
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return {
        'min_lon': min(lons), 'max_lon': max(lons),
        'min_lat': min(lats), 'max_lat': max(lats),
    }


def _extrair_coords(obj):
    """Extrai todas as coordenadas (lon, lat) de um GeoJSON."""
    coords = []
    def walk(o):
        if isinstance(o, list):
            if len(o) >= 2 and isinstance(o[0], (int, float)):
                coords.append((o[0], o[1]))
            else:
                for i in o:
                    walk(i)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(obj)
    return coords


# ─── Bounds do SVG ────────────────────────────────────────────────────────────

def obter_svg_bounds(svg_path_file):
    """
    Retorna os bounds reais dos paths do SVG (aplicando transforms).
    Importa preprocessar_svg de processar_pendentes para reusar a lógica
    já calibrada do projeto. Fallback: usa o viewBox diretamente.
    """
    try:
        from processar_pendentes import preprocessar_svg
        bounds, _ = preprocessar_svg(Path(svg_path_file))
        if bounds:
            return bounds
    except Exception:
        pass

    # Fallback: viewBox
    try:
        tree = etree.parse(str(svg_path_file))
        vb = tree.getroot().get('viewBox', '0 0 3507 2480').split()
        return {
            'min_x': float(vb[0]),
            'min_y': float(vb[1]),
            'max_x': float(vb[0]) + float(vb[2]),
            'max_y': float(vb[1]) + float(vb[3]),
            'width':  float(vb[2]),
            'height': float(vb[3]),
        }
    except Exception as e:
        print(f"   ⚠️  Erro ao ler viewBox: {e}")
    return None


# ─── Projeção geo → SVG ───────────────────────────────────────────────────────

def gerar_path_d(gj, geo_bounds, svg_bounds):
    """
    Converte as features GeoJSON do contorno em uma string de path SVG,
    usando a mesma projeção linear equiretangular do processar_pendentes.py:
      SVG_x = svg_min_x + (lon - min_lon) / lon_range * svg_width
      SVG_y = svg_min_y + (max_lat - lat) / lat_range * svg_height  (Y invertido)
    """
    min_lon   = geo_bounds['min_lon']
    max_lon   = geo_bounds['max_lon']
    min_lat   = geo_bounds['min_lat']
    max_lat   = geo_bounds['max_lat']
    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat

    sx0 = svg_bounds['min_x']
    sy0 = svg_bounds['min_y']
    sw  = svg_bounds['width']
    sh  = svg_bounds['height']

    def project(lon, lat):
        x = sx0 + (lon - min_lon) / lon_range * sw
        y = sy0 + (max_lat - lat) / lat_range * sh
        return x, y

    def ring_to_d(ring):
        if not ring:
            return ''
        # Normaliza um nível de aninhamento extra (ex: [[[lon,lat], ...]])
        if ring and isinstance(ring[0][0], list):
            ring = ring[0]
        pts = [project(c[0], c[1]) for c in ring if len(c) >= 2]
        if not pts:
            return ''
        d = f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"
        for p in pts[1:]:
            d += f" L {p[0]:.2f},{p[1]:.2f}"
        return d + " Z"

    parts = []
    for feature in gj.get('features', []):
        geom   = feature.get('geometry', {})
        tipo   = geom.get('type', '')
        coords = geom.get('coordinates', [])

        if tipo == 'Polygon':
            # Só o anel externo (índice 0) — ignoramos buracos intencionalmente
            d = ring_to_d(coords[0]) if coords else ''
            if d:
                parts.append(d)
        elif tipo == 'MultiPolygon':
            for polygon in coords:
                d = ring_to_d(polygon[0]) if polygon else ''
                if d:
                    parts.append(d)

    return ' '.join(parts)


# ─── Geração do SVG ───────────────────────────────────────────────────────────

def criar_contorno_uf(uf, variante='branco'):
    """
    Gera svg_estados/{UF}_contorno_{variante}.svg.
    Retorna o Path do arquivo gerado ou None em caso de erro.
    """
    uf = uf.upper()
    codigo = CODIGOS_UF.get(uf)
    if not codigo:
        print(f"   ❌ UF desconhecida: {uf}")
        return None

    # SVG de referência para extrair bounds e viewBox
    svg_ref = PASTA_SVG / f"{uf}_{variante}.svg"
    if not svg_ref.exists():
        alt = 'preto' if variante == 'branco' else 'branco'
        svg_ref = PASTA_SVG / f"{uf}_{alt}.svg"
        if not svg_ref.exists():
            print(f"   ❌ Nenhum SVG de referência encontrado em {PASTA_SVG} para {uf}")
            return None

    print(f"   📐 Bounds do SVG ({svg_ref.name})...")
    svg_bounds = obter_svg_bounds(svg_ref)
    if not svg_bounds:
        print(f"   ❌ Falha ao calcular bounds do SVG")
        return None
    print(f"      x({svg_bounds['min_x']:.0f}–{svg_bounds['max_x']:.0f})"
          f"  y({svg_bounds['min_y']:.0f}–{svg_bounds['max_y']:.0f})")

    print(f"   🌐 Bounds geográficos do estado (mesma fonte que processar_pendentes)...")
    try:
        from processar_pendentes import baixar_bounds_estado
        geo_bounds = baixar_bounds_estado(uf)
    except Exception:
        geo_bounds = baixar_geo_bounds(codigo)
    if not geo_bounds:
        print(f"   ❌ Falha ao calcular bounds geográficos")
        return None
    print(f"      lon({geo_bounds['min_lon']:.2f}–{geo_bounds['max_lon']:.2f})"
          f"  lat({geo_bounds['min_lat']:.2f}–{geo_bounds['max_lat']:.2f})")

    print(f"   📥 Baixando contorno (resolução 4)...")
    gj = baixar_geojson_contorno(codigo, resolucao=4)
    if not gj:
        print(f"   ❌ Falha ao baixar GeoJSON de contorno")
        return None

    print(f"   🔄 Convertendo GeoJSON → path SVG...")
    path_d = gerar_path_d(gj, geo_bounds, svg_bounds)
    if not path_d:
        print(f"   ❌ Falha ao converter GeoJSON para path")
        return None

    # Lê viewBox do SVG de referência para manter o mesmo sistema de coords
    tree    = etree.parse(str(svg_ref))
    viewbox = tree.getroot().get('viewBox', '0 0 3507 2480')

    stroke_cor = COR_BRANCO if variante == 'branco' else COR_PRETO

    svg_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">\n'
        f'  <!-- Contorno externo {uf} · stroke grosso para estilo V1-d -->\n'
        f'  <path d="{path_d}"\n'
        f'        fill="none"\n'
        f'        stroke="{stroke_cor}"\n'
        f'        stroke-width="{STROKE_CONTORNO}"\n'
        f'        stroke-linejoin="round"\n'
        f'        stroke-linecap="round"/>\n'
        '</svg>\n'
    )

    saida = PASTA_SVG / f"{uf}_contorno_{variante}.svg"
    saida.write_text(svg_content, encoding='utf-8')
    print(f"   ✅ {saida.name}")
    return saida


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Gera SVG de contorno dos estados (sem bordas municipais)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python criar_contorno.py --uf PR
  python criar_contorno.py --uf PR SC RS
  python criar_contorno.py --uf PR SC RS GO MS MT DF
  python criar_contorno.py --todos
        """,
    )
    parser.add_argument('--uf', nargs='+', metavar='UF',
                        help="Siglas dos estados (ex: PR SC RS)")
    parser.add_argument('--todos', action='store_true',
                        help="Gerar para todos os estados com SVG em svg_estados/")
    args = parser.parse_args()

    if args.todos:
        ufs = sorted({
            f.stem.split('_')[0].upper()
            for f in PASTA_SVG.glob('*_branco.svg')
            if '_contorno_' not in f.stem
        })
    elif args.uf:
        ufs = [u.upper() for u in args.uf]
    else:
        parser.print_help()
        return

    print(f"\n{'='*60}")
    print(f"   CRIAR SVG DE CONTORNO — {len(ufs)} estado(s): {', '.join(ufs)}")
    print(f"{'='*60}")

    ok = erros = 0
    for uf in ufs:
        print(f"\n[{uf}]")
        for variante in ('branco', 'preto'):
            try:
                r = criar_contorno_uf(uf, variante)
                if r:
                    ok += 1
                else:
                    erros += 1
            except Exception as e:
                print(f"   ❌ {variante}: {e}")
                import traceback; traceback.print_exc()
                erros += 1

    print(f"\n{'='*60}")
    print(f"   ✅ {ok} arquivos gerados  |  ❌ {erros} erros")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
