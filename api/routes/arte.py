import io
import logging
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
log = logging.getLogger("map_engine.arte")

_MAX_LOC = int(os.environ.get("MAX_LOCALIDADES", "10"))


def _arte_response(req: ArteRequest) -> Response:
    if len(req.localidades) > _MAX_LOC:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {_MAX_LOC} localidades por requisição",
        )
    t0 = time.perf_counter()
    try:
        t_a = time.perf_counter()
        localidades_resolvidas = resolver_localidades(req.localidades)
        ms_resolve = int((time.perf_counter() - t_a) * 1000)

        t_b = time.perf_counter()
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
        ms_gerar = int((time.perf_counter() - t_b) * 1000)

        t_c = time.perf_counter()
        buf = io.BytesIO()
        if req.resolucao == "preview":
            img.save(buf, format="PNG", compress_level=3)
        else:
            img.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()
        ms_png = int((time.perf_counter() - t_c) * 1000)

        render_time = int((time.perf_counter() - t0) * 1000)
        log.info(
            "arte_timing estilo=%s resolucao=%s cor=%s resolve_ms=%s gerar_ms=%s png_ms=%s total_ms=%s locs=%s",
            req.estilo,
            req.resolucao,
            req.cor,
            ms_resolve,
            ms_gerar,
            ms_png,
            render_time,
            len(localidades_resolvidas),
        )
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Render-Time": str(render_time),
                "X-Time-Resolve-Ms": str(ms_resolve),
                "X-Time-Gerar-Ms": str(ms_gerar),
                "X-Time-Png-Ms": str(ms_png),
                "X-Localidades": str(len(localidades_resolvidas)),
                "Cache-Control": "no-store",
            },
        )
    except LocalidadeNaoEncontrada as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração: {e!s}") from e


@router.get("/estilos")
async def listar_estilos():
    return [
        {
            "id": "completa",
            "nome": "Completa",
            "descricao": "Mapa pintado + LÁ DE + linha ao centroide (Kesong)",
        },
        {
            "id": "v1a",
            "nome": "V1-A",
            "descricao": "Mapa isolado + contorno + tipografia (multi-município mesmo UF)",
        },
        {"id": "v1d", "nome": "V1-D", "descricao": "Bordas internas + anel de contorno + destaque"},
        {"id": "v1d2", "nome": "V1-D2", "descricao": "Variação V1-D (vis menor, tipografia ajustada)"},
        {"id": "v1e", "nome": "V1-E", "descricao": "Retrofia + Grotesk + mapa estilo V1-D"},
        {"id": "v2c", "nome": "V2-C", "descricao": "Mapa + ano de fundação + Fraunces"},
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
