"""Placeholder art until `arte-lojas` gerar_arte_*.py are migrated here."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


def gerar_placeholder(
    localidades: list[dict],
    opcoes: dict | None,
    estilo: str,
) -> PILImage:
    opcoes = opcoes or {}
    resolucao = opcoes.get("resolucao", "preview")
    w, h = (800, 920) if resolucao == "preview" else (3200, 3680)
    cor = opcoes.get("cor", "preto")
    if cor == "branco":
        bg = (242, 240, 239)
        fg = (42, 46, 34)
    else:
        bg = (14, 15, 11)
        fg = (214, 186, 141)

    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    loc_str = ", ".join(f"{d['municipio']}/{d['uf']}" for d in localidades)
    texto1 = opcoes.get("texto_linha1", "")
    texto2 = opcoes.get("texto_linha2", "")
    lines = [
        "map-engine · scaffold",
        f"estilo={estilo} · resolucao={resolucao}",
        texto1,
        texto2,
        loc_str[:200],
    ]
    y = int(h * 0.08)
    for line in lines:
        draw.text((int(w * 0.06), y), str(line)[:100], fill=fg)
        y += int(h * 0.06)
    draw.rectangle(
        (int(w * 0.06), int(h * 0.45), int(w * 0.94), int(h * 0.88)),
        outline=fg,
        width=max(2, w // 400),
    )
    return img
