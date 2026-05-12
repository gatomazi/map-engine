import os
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.limiter import limiter
from api.middleware.request_timing import RequestTimingMiddleware
from api.routes import arte, batch, validar

app = FastAPI(title="Map Engine API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=[
        "X-Render-Time",
        "X-Request-Time-Ms",
        "X-Time-Resolve-Ms",
        "X-Time-Gerar-Ms",
        "X-Time-Png-Ms",
        "X-Localidades",
    ],
)
app.add_middleware(RequestTimingMiddleware)

app.include_router(arte.router)
app.include_router(batch.router)
app.include_router(validar.router)


def _assets_ok() -> bool:
    root = Path(__file__).resolve().parent.parent
    assets = Path(os.environ.get("ASSETS_DIR", str(root / "assets")))
    font = assets / "font"
    svg = assets / "svg_estados"
    return font.is_dir() and svg.is_dir() and any(svg.glob("*.svg"))


def _ibge_ok() -> bool:
    try:
        r = requests.get(
            "https://servicodados.ibge.gov.br/api/v1/localidades/estados/SC",
            timeout=3,
        )
        return r.status_code == 200
    except Exception:
        return False


@app.get("/health")
def health():
    return {
        "ok": True,
        "assets_ok": _assets_ok(),
        "ibge_ok": _ibge_ok(),
    }
