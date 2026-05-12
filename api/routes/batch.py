import io
import os
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, Header, HTTPException

from api.models import BatchEstadoBody
from engine.dispatcher import ESTILOS, gerar as dispatch_gerar
from engine.utils.pintar_municipio import normalizar_nome

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


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _slug_arquivo(nome_municipio: str) -> str:
    return normalizar_nome(nome_municipio).replace(" ", "_")


def _output_root() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return Path(os.environ.get("OUTPUT_DIR", str(root / ".data" / "output")))


def _listar_municipios_ibge(uf: str) -> list[dict]:
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def _municipios_alvo(uf: str, filtro: list[str]) -> list[dict]:
    todos = _listar_municipios_ibge(uf)
    if any(x.strip().lower() == "todos" for x in filtro):
        return [{"municipio": m["nome"], "uf": uf} for m in todos]
    want = {_norm(x) for x in filtro}
    out: list[dict] = []
    for m in todos:
        if _norm(m["nome"]) in want:
            out.append({"municipio": m["nome"], "uf": uf})
    return out


@router.post("/estado/{uf}")
def batch_estado(
    uf: str,
    body: BatchEstadoBody,
    _: None = Depends(_require_api_key),
):
    """
    Gera PNGs em disco para municípios do UF (uso interno).
    Limite: BATCH_MAX_MUNICIPIOS (padrão 40) para evitar timeout.
    """
    if len(uf) != 2:
        raise HTTPException(status_code=400, detail="UF deve ter 2 letras")
    uf = uf.upper()

    estilos = [e for e in body.estilos if e in ESTILOS]
    if not estilos:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum estilo válido. Opções: {sorted(ESTILOS)}",
        )

    max_m = int(os.environ.get("BATCH_MAX_MUNICIPIOS", "40"))
    alvo = _municipios_alvo(uf, body.municipios)
    if not alvo:
        raise HTTPException(
            status_code=404,
            detail="Nenhum município encontrado para o filtro informado",
        )
    if len(alvo) > max_m:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {max_m} municípios por batch (encontrados {len(alvo)}). "
            "Aumente BATCH_MAX_MUNICIPIOS ou restrinja a lista.",
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_dir = _output_root() / "batch" / uf / run_id
    base_dir.mkdir(parents=True, exist_ok=True)

    gerados = 0
    erros: list[dict] = []
    paths: list[str] = []

    for loc in alvo:
        nome = loc["municipio"]
        slug = _slug_arquivo(nome)
        for estilo in estilos:
            t0 = time.time()
            try:
                img = dispatch_gerar(
                    localidades=[loc],
                    texto_linha1=body.texto_linha1,
                    texto_linha2=nome,
                    texto_legenda=body.texto_legenda,
                    posicao=body.posicao,
                    estilo=estilo,
                    cor=body.cor,
                    resolucao=body.resolucao,
                )
                out_dir = base_dir / estilo
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{slug}_{body.cor}.png"
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                out_path.write_bytes(buf.getvalue())
                gerados += 1
                paths.append(str(out_path))
            except Exception as e:
                erros.append(
                    {
                        "municipio": nome,
                        "estilo": estilo,
                        "erro": str(e),
                        "ms": int((time.time() - t0) * 1000),
                    }
                )

    return {
        "uf": uf,
        "run_id": run_id,
        "pasta": str(base_dir),
        "estilos": estilos,
        "municipios_processados": len(alvo),
        "png_gerados": gerados,
        "erros": erros,
        "arquivos": paths,
    }
