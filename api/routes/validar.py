from pathlib import Path
import os

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["validar"], prefix="/validar")


def _assets_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return Path(os.environ.get("ASSETS_DIR", str(root / "assets")))


@router.get("/{uf}")
def validar_uf(uf: str):
    """Checa se há SVG base do estado em assets (validação leve)."""
    if len(uf) != 2:
        raise HTTPException(status_code=400, detail="UF inválida")
    uf = uf.upper()
    svg_dir = _assets_dir() / "svg_estados"
    candidatos = list(svg_dir.glob(f"{uf}*.svg")) if svg_dir.is_dir() else []
    return {
        "uf": uf,
        "svg_estados_dir": str(svg_dir),
        "arquivos_encontrados": len(candidatos),
        "ok": len(candidatos) > 0,
    }
