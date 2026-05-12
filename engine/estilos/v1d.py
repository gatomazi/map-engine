"""
Estilo V1-D — migrado de arte-lojas/gerar_arte_v1d.py.
Bordas municipais finas + anel de contorno + município(s) em destaque.
"""

from __future__ import annotations

import io
import os
import re
import unicodedata
from pathlib import Path

import cairosvg
import numpy as np
import requests
from lxml import etree
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine.utils import svg_pendentes as _sp

# ─── Paths ────────────────────────────────────────────────────────────────────


def _assets_dir() -> Path:
    return Path(
        os.environ.get(
            "ASSETS_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "assets"),
        )
    )


PASTA_SVG = _assets_dir() / "svg_estados"

FONT_FRAUNCES = _assets_dir() / "font" / "Fraunces" / "static" / "Fraunces_72pt-Black.ttf"
FONT_GROTESK = _assets_dir() / "font" / "Space_Grotesk" / "static" / "SpaceGrotesk-Medium.ttf"
FONT_KESONG = _assets_dir() / "font" / "xiangcui-kesong" / "kesong-latest.ttf"
if not FONT_FRAUNCES.exists():
    FONT_FRAUNCES = FONT_KESONG
if not FONT_GROTESK.exists():
    FONT_GROTESK = FONT_KESONG

# ─── Canvas ─────────────────────────────────────────────────────────────────────
CANVAS_W = 4270
CANVAS_H = 4900

UF_CONFIG = {
    "SC": dict(vis_x=373, vis_y=590, vis_w=3544),
    "PR": dict(vis_x=383, vis_y=544, vis_w=3609),
    "RS": dict(vis_x=501, vis_y=575, vis_w=3307),
    "GO": dict(vis_x=625, vis_y=557, vis_w=3029),
    "MS": dict(vis_x=579, vis_y=564, vis_w=3160),
    "MT": dict(vis_x=622, vis_y=550, vis_w=3057),
    "DF": dict(vis_x=700, vis_y=557, vis_w=2900),
    "AC": dict(vis_x=344, vis_y=661, vis_w=3716),
    "AM": dict(vis_x=239, vis_y=665, vis_w=3779),
    "AP": dict(vis_x=758, vis_y=660, vis_w=2594),
    "PA": dict(vis_x=708, vis_y=662, vis_w=3063),
    "RO": dict(vis_x=344, vis_y=669, vis_w=3527),
    "RR": dict(vis_x=741, vis_y=667, vis_w=2624),
    "TO": dict(vis_x=1231, vis_y=664, vis_w=1817),
}
_DEFAULT_CFG = dict(vis_x=373, vis_y=590, vis_w=3544)

BG_V1D = (0, 0, 0, 0)
STROKE_FINO = 2.0
TEXTO_SX = 0.75
TEXTO_SY = 1.55

_PALETAS = {
    "escura": dict(
        outline=(0, 0, 0, 255),
        text=(0, 0, 0, 255),
        mun_fill="#4d543d",
        stroke_cor="#000000",
    ),
    "clara": dict(
        outline=(255, 255, 255, 255),
        text=(242, 240, 239, 255),
        mun_fill="#d6ba8d",
        stroke_cor="#ffffff",
    ),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _fonte(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _quebrar_nome(nome: str, limite: int = 20) -> str:
    if len(nome) <= limite:
        return nome
    palavras = nome.split()
    melhor, melhor_diff = nome, len(nome)
    for i in range(1, len(palavras)):
        l1 = " ".join(palavras[:i])
        l2 = " ".join(palavras[i:])
        diff = abs(len(l1) - len(l2))
        if diff < melhor_diff:
            melhor_diff, melhor = diff, l1 + "\n" + l2
    return melhor


def _fonte_cidade(nome: str, max_w: int = 2700) -> ImageFont.FreeTypeFont:
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    txt = _quebrar_nome(nome).upper()
    for size in range(420, 110, -10):
        f = _fonte(FONT_FRAUNCES, size)
        w = max(d.textbbox((0, 0), ln, font=f)[2] for ln in txt.split("\n"))
        if w * TEXTO_SX <= max_w:
            return f
    return _fonte(FONT_FRAUNCES, 120)


def _render_cidade(
    nome: str,
    font: ImageFont.FreeTypeFont,
    cor: tuple = (242, 240, 239, 255),
) -> Image.Image:
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    txt = _quebrar_nome(nome).upper()
    m = 10
    bb = d.multiline_textbbox((0, 0), txt, font=font)
    tmp = Image.new("RGBA", (bb[2] - bb[0] + m * 2, bb[3] - bb[1] + m * 2), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).multiline_text(
        (m - bb[0], m - bb[1]), txt, font=font, fill=cor, align="center"
    )
    nw = int(round(tmp.width * TEXTO_SX))
    nh = int(round(tmp.height * TEXTO_SY))
    return tmp.resize((nw, nh), Image.LANCZOS)


def _pintar_municipio(
    tree,
    uf: str,
    nome_cidade: str,
    mun_fill: str = "#d6ba8d",
) -> None:
    svg_path = PASTA_SVG / f"{uf}_branco.svg"
    muns = requests.get(
        f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
        timeout=20,
    ).json()
    codigo = next(
        (m["id"] for m in muns if _norm(m["nome"]) == _norm(nome_cidade)), None
    )
    if not codigo:
        raise ValueError(f"Município não encontrado no IBGE: {nome_cidade}/{uf}")

    gj = requests.get(
        f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}"
        "?formato=application/vnd.geo+json&qualidade=minima",
        timeout=20,
    ).json()
    bounds_mun = _sp.calcular_bounds_coords(_sp.extrair_todas_coordenadas(gj))
    bounds_est = _sp.baixar_bounds_estado(uf)
    bounds_svg, paths_info = _sp.preprocessar_svg(svg_path)

    if not (bounds_mun and bounds_est and bounds_svg and paths_info):
        raise ValueError("Bounds incompletos")

    bounds_mun_svg = _sp.calcular_bounds_municipio_em_svg(
        bounds_mun, bounds_est, bounds_svg
    )
    melhor = _sp.encontrar_melhor_path(paths_info, bounds_mun_svg, nome_cidade)
    if not melhor:
        raise ValueError("Path do município não encontrado no SVG")

    path_el = None
    if melhor.get("elem_id"):
        for e in tree.iter():
            if e.get("id") == melhor["elem_id"]:
                path_el = e
                break
    if path_el is None and melhor.get("d_prefix"):
        for e in tree.iter():
            if e.get("d", "").startswith(melhor["d_prefix"]):
                path_el = e
                break

    if path_el is None:
        raise ValueError("Elemento SVG não re-localizado")

    style = path_el.get("style", "")
    style = re.sub(r"fill:[^;]+", f"fill:{mun_fill}", style)
    if "fill:" not in style:
        style += f";fill:{mun_fill}"
    style = re.sub(r"fill-opacity:[^;]+", "fill-opacity:1", style)
    if "fill-opacity:" not in style:
        style += ";fill-opacity:1"
    path_el.set("style", style)


def _svg_v1d(
    uf: str,
    nomes_cidades: list[str],
    mun_fill: str = "#d6ba8d",
    stroke_cor: str = "#ffffff",
) -> bytes:
    svg_file = PASTA_SVG / f"{uf}_branco.svg"
    if not svg_file.is_file():
        raise FileNotFoundError(f"SVG não encontrado: {svg_file}")

    svg_str = svg_file.read_text(encoding="utf-8")
    svg_str = svg_str.replace("fill:#000000", "fill:#ffffff")
    svg_str = re.sub(r'stroke:[^;}"\']+', f"stroke:{stroke_cor}", svg_str)
    svg_str = re.sub(
        r"stroke-width:[\d.eE+-]+", f"stroke-width:{STROKE_FINO}", svg_str
    )

    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.fromstring(svg_str.encode("utf-8"), parser)

    for nome in nomes_cidades:
        try:
            _pintar_municipio(tree, uf, nome, mun_fill=mun_fill)
        except Exception as e:
            raise ValueError(f"Falha ao pintar município {nome}/{uf}: {e}") from e

    return etree.tostring(tree, encoding="unicode").encode("utf-8")


def _svg_para_img(
    svg_bytes: bytes,
    vis_w: int,
    crop_box: tuple | None = None,
    dpi: int | None = None,
) -> tuple[Image.Image, tuple]:
    if dpi is None:
        dpi = int(os.environ.get("FINAL_DPI", "300"))
    png = cairosvg.svg2png(bytestring=svg_bytes, dpi=dpi)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    if crop_box is None:
        arr = np.array(img)
        vis = arr[:, :, 3] > 10
        ys, xs = np.where(vis)
        if len(xs) == 0:
            return img, (0, 0, img.width - 1, img.height - 1)
        pad = 20
        crop_box = (
            max(0, int(xs.min()) - pad),
            max(0, int(ys.min()) - pad),
            min(img.width - 1, int(xs.max()) + pad),
            min(img.height - 1, int(ys.max()) + pad),
        )
    x0, y0, x1, y1 = crop_box
    cropped = img.crop((x0, y0, x1 + 1, y1 + 1))
    scale = vis_w / (x1 - x0 + 1)
    resized = cropped.resize(
        (vis_w, int(round((y1 - y0 + 1) * scale))), Image.LANCZOS
    )
    return resized, crop_box


def _svg_solido_bytes(uf: str) -> bytes:
    svg_str = (PASTA_SVG / f"{uf}_branco.svg").read_text(encoding="utf-8")
    svg_str = re.sub(r'fill:[^;}"\']+', "fill:#ffffff", svg_str)
    svg_str = re.sub(r'fill-opacity:[^;}"\']+', "fill-opacity:1", svg_str)
    svg_str = re.sub(r'stroke:[^;}"\']+', "stroke:none", svg_str)
    return svg_str.encode("utf-8")


def _criar_contorno_img(
    img_mun: Image.Image,
    uf: str,
    vis_w: int,
    crop_box: tuple,
    ring_px: int = 13,
    cor: tuple = (255, 255, 255, 255),
    dpi: int | None = None,
) -> Image.Image:
    img_solid, _ = _svg_para_img(
        _svg_solido_bytes(uf), vis_w, crop_box=crop_box, dpi=dpi
    )
    solid_mask = np.array(img_solid)[:, :, 3] > 10
    solid_pil = Image.fromarray((solid_mask * 255).astype(np.uint8), "L")

    rs = ring_px * 2 + 1
    outer = np.array(solid_pil.filter(ImageFilter.MaxFilter(rs))) > 0
    ring = outer & ~solid_mask

    out = np.zeros((img_mun.height, img_mun.width, 4), dtype=np.uint8)
    out[ring] = list(cor)
    return Image.fromarray(out, "RGBA")


def _off_y_mapa(posicao: str, base_off: int, map_h: int) -> int:
    """Posição vertical do mapa abaixo do texto (top / center / bottom)."""
    if posicao == "center":
        return base_off + max(0, (CANVAS_H - base_off - map_h) // 3)
    if posicao == "bottom":
        return max(base_off, CANVAS_H - map_h - 100)
    return base_off


def gerar(localidades: list[dict], opcoes: dict | None = None) -> Image.Image:
    opcoes = opcoes or {}
    if not localidades:
        raise ValueError("localidades vazia")

    ufs = {loc["uf"].upper() for loc in localidades}
    if len(ufs) != 1:
        raise ValueError(
            "V1-D: todas as localidades precisam ser do mesmo estado (mesmo UF)"
        )
    uf = next(iter(ufs))
    nomes_ibge = [loc["municipio"] for loc in localidades]

    cor_req = opcoes.get("cor", "preto")
    versao = "escura" if cor_req == "preto" else "clara"
    pal = _PALETAS[versao]

    texto_linha1 = opcoes.get("texto_linha1", "Lá de")
    texto_linha2 = opcoes.get("texto_linha2") or nomes_ibge[0]
    posicao = opcoes.get("posicao", "center")
    resolucao = opcoes.get("resolucao", "preview")

    if resolucao == "preview":
        dpi = int(os.environ.get("PREVIEW_SVG_DPI", "96"))
        max_dim = int(os.environ.get("PREVIEW_MAX_DIM", "800"))
    else:
        dpi = int(os.environ.get("FINAL_DPI", "300"))
        max_dim = None

    cfg = UF_CONFIG.get(uf, _DEFAULT_CFG)
    vis_x = cfg["vis_x"]
    vis_w = cfg["vis_w"]

    font_city = _fonte_cidade(texto_linha2)
    img_cidade = _render_cidade(texto_linha2, font_city, cor=pal["text"])
    img_label = _render_cidade(texto_linha1, _fonte(FONT_FRAUNCES, 140), cor=pal["text"])

    svg_bytes = _svg_v1d(
        uf,
        nomes_ibge,
        mun_fill=pal["mun_fill"],
        stroke_cor=pal["stroke_cor"],
    )
    img_mun, crop_box = _svg_para_img(svg_bytes, vis_w, dpi=dpi)
    img_cont = _criar_contorno_img(
        img_mun, uf, vis_w, crop_box, cor=pal["outline"], dpi=dpi
    )

    TEXT_TOP = 130
    GAP_LABEL = 20
    label_top = TEXT_TOP
    city_top = label_top + img_label.height + GAP_LABEL
    base_off = city_top + img_cidade.height + 80
    off_y = _off_y_mapa(posicao, base_off, img_mun.height)

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_V1D)
    canvas.paste(img_mun, (vis_x, off_y), img_mun)
    canvas.paste(img_cont, (vis_x, off_y), img_cont)
    canvas.paste(
        img_label, (CANVAS_W // 2 - img_label.width // 2, label_top), img_label
    )
    canvas.paste(
        img_cidade,
        (CANVAS_W // 2 - img_cidade.width // 2, city_top),
        img_cidade,
    )

    if max_dim and max(canvas.size) > max_dim:
        canvas.thumbnail((max_dim, max_dim), Image.LANCZOS)

    return canvas
