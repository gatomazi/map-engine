import os

from fastapi import APIRouter, Depends, Header, HTTPException

from api.models import BatchEstadoBody

router = APIRouter(tags=["batch"], prefix="/batch")


def _require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.environ.get("API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Batch desabilitado: defina API_KEY no ambiente",
        )
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="API_KEY inválida")


@router.post("/estado/{uf}")
def batch_estado(
    uf: str,
    body: BatchEstadoBody,
    _: None = Depends(_require_api_key),
):
    """
    Regenera artes por estado (uso interno). Corpo ainda não executa pipeline —
    migrar lógica de batch de `arte-lojas` após estilos reais.
    """
    if len(uf) != 2:
        raise HTTPException(status_code=400, detail="UF deve ter 2 letras")
    return {
        "uf": uf.upper(),
        "estilos": body.estilos,
        "municipios": body.municipios,
        "status": "queued_stub",
        "mensagem": "Implementar batch após migração dos geradores",
    }
