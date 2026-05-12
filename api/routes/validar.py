from pathlib import Path
import os

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["validar"], prefix="/validar")


def _assets_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return Path(os.environ.get("ASSETS_DIR", str(root / "assets")))


@router.get("/{uf}")
def validar_uf(uf: str):
    """Checa SVGs base do estado (padrão arte-lojas: UF_branco.svg / UF_preto.svg)."""
    if len(uf) != 2:
        raise HTTPException(status_code=400, detail="UF inválida")
    uf = uf.upper()
    svg_dir = _assets_dir() / "svg_estados"
    branco = svg_dir / f"{uf}_branco.svg"
    preto = svg_dir / f"{uf}_preto.svg"
    candidatos = list(svg_dir.glob(f"{uf}*.svg")) if svg_dir.is_dir() else []
    return {
        "uf": uf,
        "svg_estados_dir": str(svg_dir),
        "tem_branco": branco.is_file(),
        "tem_preto": preto.is_file(),
        "arquivos_encontrados": len(candidatos),
        "ok": branco.is_file() and preto.is_file(),
    }
