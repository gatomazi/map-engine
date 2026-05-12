"""Estilo V1-A — migrado de arte-lojas/gerar_arte_v1a.py (contorno fino + município gold)."""

from __future__ import annotations

import io
import os
import re
import unicodedata
from pathlib import Path

import cairosvg
import numpy as np
from lxml import etree
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine.utils.svg_municipio_paint import pintar_municipio_no_tree

CANVAS_W = 4270
CANVAS_H = 4900

UF_CONFIG = {
    "SC": dict(vis_w=3544),
    "PR": dict(vis_w=3609),
    "RS": dict(vis_w=3307),
    "GO": dict(vis_w=3029),
    "MS": dict(vis_w=3160),
    "MT": dict(vis_w=3057),
    "DF": dict(vis_w=2900),
    "AC": dict(vis_w=3716),
    "AM": dict(vis_w=3779),
    "AP": dict(vis_w=2594),
    "PA": dict(vis_w=3063),
    "RO": dict(vis_w=3527),
    "RR": dict(vis_w=2624),
    "TO": dict(vis_w=1817),
}
_DEFAULT_CFG = dict(vis_w=3544)

BG = (0, 0, 0, 0)
OUTLINE_PX = 13

_PALETAS = {
    "escura": dict(
        outline=(0, 0, 0, 255),
        text=(0, 0, 0, 255),
        mun_fill="#4d543d",
        rule=(77, 84, 61, 180),
    ),
    "clara": dict(
        outline=(255, 255, 255, 255),
        text=(242, 240, 239, 255),
        mun_fill="#d6ba8d",
        rule=(214, 186, 141, 180),
    ),
}


def _assets_dir() -> Path:
    return Path(
        os.environ.get(
            "ASSETS_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "assets"),
        )
    )


PASTA_SVG = _assets_dir() / "svg_estados"
FONT_FRAUNCES = _assets_dir() / "font" / "Fraunces" / "static" / "Fraunces_72pt-Black.ttf"
FONT_KESONG = _assets_dir() / "font" / "xiangcui-kesong" / "kesong-latest.ttf"
if not FONT_FRAUNCES.exists():
    FONT_FRAUNCES = FONT_KESONG


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


def _fonte_cidade(nome: str, max_w: int = 3300) -> ImageFont.FreeTypeFont:
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    txt = _quebrar_nome(nome).upper()
    for size in range(370, 110, -10):
        f = _fonte(FONT_FRAUNCES, size)
        w = max(d.textbbox((0, 0), ln, font=f)[2] for ln in txt.split("\n"))
        if w <= max_w:
            return f
    return _fonte(FONT_FRAUNCES, 120)


def _svg_solido_bytes(uf: str) -> bytes:
    svg_str = (PASTA_SVG / f"{uf}_branco.svg").read_text(encoding="utf-8")
    svg_str = svg_str.replace("fill:#000000", "fill:#ffffff")
    svg_str = re.sub(r'fill:[^;}"\']+', "fill:#ffffff", svg_str)
    svg_str = re.sub(r'fill-opacity:[^;}"\']+', "fill-opacity:1", svg_str)
    svg_str = re.sub(r'stroke:[^;}"\']+', "stroke:none", svg_str)
    return svg_str.encode("utf-8")


def _svg_municipio_isolado(uf: str, nomes_cidades: list[str], mun_fill: str) -> bytes:
    svg_file = PASTA_SVG / f"{uf}_branco.svg"
    svg_str = svg_file.read_text(encoding="utf-8")
    svg_str = svg_str.replace("fill:#000000", "fill:#ffffff")
    svg_str = re.sub(r'fill:[^;}"\']+', "fill:none", svg_str)
    svg_str = re.sub(r'fill-opacity:[^;}"\']+', "fill-opacity:0", svg_str)
    svg_str = re.sub(r'stroke:[^;}"\']+', "stroke:none", svg_str)
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.fromstring(svg_str.encode("utf-8"), parser)
    for nome in nomes_cidades:
        pintar_municipio_no_tree(tree, uf, nome, mun_fill, PASTA_SVG)
    return etree.tostring(tree, encoding="unicode").encode("utf-8")


def _svg_para_img(
    svg_bytes: bytes, vis_w: int, crop_box: tuple | None = None, dpi: int | None = None
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


def _criar_outline_estado(
    img_solid: Image.Image, ring_px: int = OUTLINE_PX, cor: tuple = (255, 255, 255, 255)
) -> Image.Image:
    arr = np.array(img_solid)
    solid = arr[:, :, 3] > 10
    solid_pil = Image.fromarray((solid * 255).astype(np.uint8), "L")
    solid_pil = solid_pil.filter(ImageFilter.MaxFilter(11)).filter(ImageFilter.MinFilter(11))
    solid = np.array(solid_pil) > 0
    rs = ring_px * 2 + 1
    outer = np.array(solid_pil.filter(ImageFilter.MaxFilter(rs))) > 0
    ring = outer & ~solid
    out = np.zeros((img_solid.height, img_solid.width, 4), dtype=np.uint8)
    out[ring] = list(cor)
    return Image.fromarray(out, "RGBA")


def gerar(localidades: list[dict], opcoes: dict | None = None) -> Image.Image:
    opcoes = opcoes or {}
    if not localidades:
        raise ValueError("localidades vazia")
    ufs = {loc["uf"].upper() for loc in localidades}
    if len(ufs) != 1:
        raise ValueError("V1-A: todas as localidades devem ser do mesmo UF")
    uf = next(iter(ufs))
    nomes = [loc["municipio"] for loc in localidades]

    cor_req = opcoes.get("cor", "preto")
    versao = "escura" if cor_req == "preto" else "clara"
    pal = _PALETAS[versao]
    texto_linha2 = opcoes.get("texto_linha2") or nomes[0]
    resolucao = opcoes.get("resolucao", "preview")
    if resolucao == "preview":
        dpi = int(os.environ.get("PREVIEW_SVG_DPI", "96"))
        max_dim = int(os.environ.get("PREVIEW_MAX_DIM", "800"))
    else:
        dpi = int(os.environ.get("FINAL_DPI", "300"))
        max_dim = None

    cfg = UF_CONFIG.get(uf, _DEFAULT_CFG)
    vis_w = cfg["vis_w"]

    img_solid, crop_box = _svg_para_img(_svg_solido_bytes(uf), vis_w, dpi=dpi)
    img_outline = _criar_outline_estado(img_solid, cor=pal["outline"])
    img_mun, _ = _svg_para_img(
        _svg_municipio_isolado(uf, nomes, mun_fill=pal["mun_fill"]),
        vis_w,
        crop_box=crop_box,
        dpi=dpi,
    )

    txt_cidade = _quebrar_nome(texto_linha2).upper()
    font_city = _fonte_cidade(texto_linha2)
    d_tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = d_tmp.multiline_textbbox((0, 0), txt_cidade, font=font_city)
    city_h = bb[3] - bb[1]

    map_top = 200
    map_vis_x = (CANVAS_W - vis_w) // 2
    map_bottom = map_top + img_solid.height
    divider_y = map_bottom + 80
    city_center = divider_y + 90 + city_h // 2

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG)
    canvas.paste(img_outline, (map_vis_x, map_top), img_outline)
    canvas.paste(img_mun, (map_vis_x, map_top), img_mun)

    draw = ImageDraw.Draw(canvas)
    draw.line(
        [(CANVAS_W // 2 - 700, divider_y), (CANVAS_W // 2 + 700, divider_y)],
        fill=pal["rule"],
        width=3,
    )
    draw.multiline_text(
        (CANVAS_W // 2, city_center),
        txt_cidade,
        font=font_city,
        fill=pal["text"],
        anchor="mm",
        align="center",
    )

    if max_dim and max(canvas.size) > max_dim:
        canvas.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return canvas
