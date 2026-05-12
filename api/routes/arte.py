import io
import os
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from api.limiter import limiter
from api.models import ArteRequest
from engine import dispatcher
from engine.utils.localidade import buscar_ibge_e_osm, resolver_localidades
from engine.utils.localidade_exceptions import LocalidadeNaoEncontrada

router = APIRouter(tags=["arte"])

_MAX_LOC = int(os.environ.get("MAX_LOCALIDADES", "10"))


def _arte_response(req: ArteRequest) -> Response:
    if len(req.localidades) > _MAX_LOC:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {_MAX_LOC} localidades por requisição",
        )
    t0 = time.time()
    try:
        localidades_resolvidas = resolver_localidades(req.localidades)
        img = dispatcher.gerar(
            localidades=localidades_resolvidas,
            texto_linha1=req.texto_linha1,
            texto_linha2=req.texto_linha2,
            texto_legenda=req.texto_legenda,
            posicao=req.posicao,
            estilo=req.estilo,
            cor=req.cor,
            resolucao=req.resolucao,
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()
        render_time = int((time.time() - t0) * 1000)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Render-Time": str(render_time),
                "X-Localidades": str(len(localidades_resolvidas)),
                "Cache-Control": "no-store",
            },
        )
    except LocalidadeNaoEncontrada as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração: {e!s}") from e


@router.get("/estilos")
async def listar_estilos():
    return [
        {
            "id": "completa",
            "nome": "Completa",
            "descricao": "Mapa completo (migrar de gerar_arte_completa.py)",
        },
        {"id": "v1a", "nome": "V1-A", "descricao": "Contorno fino + município em destaque"},
        {"id": "v1d", "nome": "V1-D", "descricao": "Bordas internas + contorno grosso"},
        {"id": "v1d2", "nome": "V1-D2", "descricao": "Variação V1-D"},
        {"id": "v1e", "nome": "V1-E", "descricao": "Estilo V1-E"},
        {"id": "v2c", "nome": "V2-C", "descricao": "Estilo V2-C"},
    ]


@router.get("/arte/status")
async def arte_status():
    return {
        "requests_estimado": None,
        "cache": "SVG em memória via engine.utils.cache",
        "nota": "stub até métricas serem ligadas",
    }


@router.get("/localidade/buscar")
async def buscar_localidade(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    return buscar_ibge_e_osm(q, limit)


@router.post("/arte")
@limiter.limit("30/minute")
def gerar_arte(request: Request, req: ArteRequest):
    del request
    return _arte_response(req)


@router.post("/arte/preview")
@limiter.limit("60/minute")
def preview_arte(request: Request, req: ArteRequest):
    del request
    preview_req = req.model_copy(update={"resolucao": "preview"})
    return _arte_response(preview_req)
