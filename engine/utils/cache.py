"""TTL cache for SVG estado (e centralização futura de caches)."""

from __future__ import annotations

import os
import time
from pathlib import Path

_svg_cache: dict[str, tuple[str, float]] = {}
SVG_CACHE_TTL = int(os.environ.get("IBGE_CACHE_TTL", "3600"))


def _default_assets() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "assets"


ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", str(_default_assets())))


def _carregar_svg_estado(uf: str) -> str:
    path = ASSETS_DIR / "svg_estados" / f"{uf.upper()}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"SVG do estado não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def get_svg_estado(uf: str) -> str:
    """Retorna conteúdo SVG do estado com cache TTL em memória."""
    now = time.time()
    uf_key = uf.upper()
    if uf_key in _svg_cache:
        content, ts = _svg_cache[uf_key]
        if now - ts < SVG_CACHE_TTL:
            return content
    content = _carregar_svg_estado(uf_key)
    _svg_cache[uf_key] = (content, now)
    return content


def clear_svg_cache() -> None:
    _svg_cache.clear()
