"""
Estilo V1-D2 — migrado de arte-lojas/gerar_arte_v1d2.py.
Como V1-D, com tipografia maior (Fraunces 550 na cidade) e mapa com vis_w reduzido por UF.
"""

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

CANVAS_W = 4270
CANVAS_H = 4900

UF_CONFIG = {
    "SC": dict(vis_x=373, vis_y=590, vis_w=2300),
    "PR": dict(vis_x=383, vis_y=544, vis_w=2350),
    "RS": dict(vis_x=501, vis_y=575, vis_w=2150),
    "GO": dict(vis_x=625, vis_y=557, vis_w=1970),
    "MS": dict(vis_x=579, vis_y=564, vis_w=2054),
    "MT": dict(vis_x=622, vis_y=550, vis_w=1987),
    "DF": dict(vis_x=700, vis_y=557, vis_w=1885),
    "AC": dict(vis_x=344, vis_y=661, vis_w=2416),
    "AM": dict(vis_x=239, vis_y=665, vis_w=2457),
    "AP": dict(vis_x=758, vis_y=660, vis_w=1686),
    "PA": dict(vis_x=708, vis_y=662, vis_w=1991),
    "RO": dict(vis_x=344, vis_y=669, vis_w=2293),
    "RR": dict(vis_x=741, vis_y=667, vis_w=1706),
    "TO": dict(vis_x=1231, vis_y=664, vis_w=1181),
}
_DEFAULT_CFG = dict(vis_x=373, vis_y=590, vis_w=2300)

BG = (0, 0, 0, 0)
STROKE_FINO = 2.0
TEXTO_SX = 0.62
TEXTO_SY = 1.70

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


def _fonte(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _quebrar_nome(nome: str, limite: int = 18, font: ImageFont.FreeTypeFont | None = None) -> str:
    if font is not None:
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        ref_w = d.textbbox((0, 0), "ALTAMIRA DO PARANÁ", font=font)[2]
        if d.textbbox((0, 0), nome.upper(), font=font)[2] <= ref_w:
            return nome
    elif len(nome) <= limite:
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


def _fonte_cidade(nome: str, max_w: int = 2400) -> ImageFont.FreeTypeFont:
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    txt = _quebrar_nome(nome).upper()
    for size in range(900, 110, -10):
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
    txt = _quebrar_nome(nome, font=font).upper()
    m = 10
    bb = d.multiline_textbbox((0, 0), txt, font=font, spacing=-15)
    tmp = Image.new("RGBA", (bb[2] - bb[0] + m * 2, bb[3] - bb[1] + m * 2), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).multiline_text(
        (m - bb[0], m - bb[1]),
        txt,
        font=font,
        fill=cor,
        align="center",
        spacing=-15,
    )
    nw = int(round(tmp.width * TEXTO_SX))
    nh = int(round(tmp.height * TEXTO_SY))
    return tmp.resize((nw, nh), Image.LANCZOS)


def _pintar_municipio(tree, uf: str, nome: str, mun_fill: str) -> None:
    pintar_municipio_no_tree(tree, uf, nome, mun_fill, PASTA_SVG)


def _svg_v1d(
    uf: str,
    nomes: list[str],
    mun_fill: str,
    stroke_cor: str,
) -> bytes:
    svg_file = PASTA_SVG / f"{uf}_branco.svg"
    if not svg_file.is_file():
        raise FileNotFoundError(f"SVG não encontrado: {svg_file}")
    svg_str = svg_file.read_text(encoding="utf-8")
    svg_str = re.sub(r'stroke:[^;}"\']+', f"stroke:{stroke_cor}", svg_str)
    svg_str = re.sub(
        r"stroke-width:[\d.eE+-]+", f"stroke-width:{STROKE_FINO}", svg_str
    )
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.fromstring(svg_str.encode("utf-8"), parser)
    for nome in nomes:
        _pintar_municipio(tree, uf, nome, mun_fill=mun_fill)
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
    return cropped.resize(
        (vis_w, int(round((y1 - y0 + 1) * scale))), Image.LANCZOS
    ), crop_box


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
    cor: tuple,
    dpi: int | None,
) -> Image.Image:
    img_solid, _ = _svg_para_img(
        _svg_solido_bytes(uf), vis_w, crop_box=crop_box, dpi=dpi
    )
    solid_mask = np.array(img_solid)[:, :, 3] > 10
    solid_pil = Image.fromarray((solid_mask * 255).astype(np.uint8), "L")
    rs = 13 * 2 + 1
    outer = np.array(solid_pil.filter(ImageFilter.MaxFilter(rs))) > 0
    ring = outer & ~solid_mask
    out = np.zeros((img_mun.height, img_mun.width, 4), dtype=np.uint8)
    out[ring] = list(cor)
    return Image.fromarray(out, "RGBA")


def _off_y_mapa(posicao: str, base_off: int, map_h: int) -> int:
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
        raise ValueError("V1-D2: todas as localidades devem ser do mesmo UF")
    uf = next(iter(ufs))
    nomes = [loc["municipio"] for loc in localidades]

    cor_req = opcoes.get("cor", "preto")
    versao = "escura" if cor_req == "preto" else "clara"
    pal = _PALETAS[versao]
    texto_linha1 = opcoes.get("texto_linha1", "LÁ DE")
    texto_linha2 = opcoes.get("texto_linha2") or nomes[0]
    posicao = opcoes.get("posicao", "center")
    resolucao = opcoes.get("resolucao", "preview")
    if resolucao == "preview":
        dpi = int(os.environ.get("PREVIEW_SVG_DPI", "96"))
        max_dim = int(os.environ.get("PREVIEW_MAX_DIM", "800"))
    else:
        dpi = int(os.environ.get("FINAL_DPI", "300"))
        max_dim = None

    cfg = UF_CONFIG.get(uf, _DEFAULT_CFG)
    vis_x, vis_w = cfg["vis_x"], cfg["vis_w"]

    font_city = _fonte(FONT_FRAUNCES, 550)
    img_cidade = _render_cidade(texto_linha2, font_city, cor=pal["text"])
    font_label = _fonte(FONT_FRAUNCES, 100)
    d_tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb_label = d_tmp.textbbox((0, 0), texto_linha1.upper(), font=font_label)
    img_label = Image.new(
        "RGBA",
        (bb_label[2] - bb_label[0] + 20, bb_label[3] - bb_label[1] + 20),
        (0, 0, 0, 0),
    )
    ImageDraw.Draw(img_label).text(
        (10 - bb_label[0], 10 - bb_label[1]),
        texto_linha1.upper(),
        font=font_label,
        fill=pal["text"],
    )

    svg_bytes = _svg_v1d(
        uf, nomes, mun_fill=pal["mun_fill"], stroke_cor=pal["stroke_cor"]
    )
    img_mun, crop_box = _svg_para_img(svg_bytes, vis_w, dpi=dpi)
    img_cont = _criar_contorno_img(
        img_mun, uf, vis_w, crop_box, cor=pal["outline"], dpi=dpi
    )

    GAP_LABEL = 20
    label_top = 130
    city_top = label_top + img_label.height + GAP_LABEL
    base_off = city_top + img_cidade.height + 80
    off_y = _off_y_mapa(posicao, base_off, img_mun.height)

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG)
    canvas.paste(img_mun, (vis_x, off_y), img_mun)
    canvas.paste(img_cont, (vis_x, off_y), img_cont)
    canvas.paste(
        img_label, (CANVAS_W // 2 - img_label.width // 2, label_top), img_label
    )
    canvas.paste(
        img_cidade, (CANVAS_W // 2 - img_cidade.width // 2, city_top), img_cidade
    )

    if max_dim and max(canvas.size) > max_dim:
        canvas.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return canvas
