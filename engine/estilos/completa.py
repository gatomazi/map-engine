from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from PIL import Image

from engine.estilos import completa_impl
from engine.utils.pintar_municipio import processar_municipio

log = logging.getLogger("map_engine.estilos.completa")


def gerar(localidades: list[dict], opcoes: dict | None = None) -> Image.Image:
    opcoes = opcoes or {}
    if not localidades:
        raise ValueError("localidades vazia")
    loc = localidades[0]
    uf = loc["uf"].strip().upper()
    nome_ibge = loc["municipio"].strip()
    nome_exibir = (opcoes.get("texto_linha2") or nome_ibge).strip()
    prefix = opcoes.get("texto_linha1")
    cor = opcoes.get("cor", "preto")
    somente_cores = ("preto",) if cor == "preto" else ("branco",)
    preview = opcoes.get("resolucao") == "preview"
    pintar_dpi = (
        int(os.environ.get("PREVIEW_PINTAR_DPI", "120"))
        if preview
        else int(os.environ.get("FINAL_DPI", "300"))
    )

    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        p_maps = td / "maps" / uf
        p_maps.mkdir(parents=True, exist_ok=True)
        t_maps = time.perf_counter()
        r = processar_municipio(
            nome_ibge,
            uf,
            pasta_uf_dest=p_maps,
            somente_cores=somente_cores,
            png_dpi=pintar_dpi,
        )
        ms_pintar = int((time.perf_counter() - t_maps) * 1000)
        if not r or not r.get("arquivos"):
            raise RuntimeError(
                f"Falha ao gerar mapas pintados para {nome_ibge}/{uf} "
                "(verifique ASSETS_DIR/svg_estados e conectividade IBGE)."
            )
        by_cor = {a["cor"]: Path(a["png"]) for a in r["arquivos"] if a}
        map_b = by_cor.get("branco")
        map_p = by_cor.get("preto")
        # Arte "preto" usa mapa pintado no SVG preto; "branco" usa SVG branco — geometria igual.
        if map_b is None and map_p is not None:
            map_b = map_p
        if map_p is None and map_b is not None:
            map_p = map_b
        if not map_b or not map_p or not map_b.is_file() or not map_p.is_file():
            raise RuntimeError(
                f"PNG branco/preto incompleto após pintar: {by_cor!r}"
            )

        nome_oficial = r["municipio"]
        n_arq = completa_impl.nome_arquivo(nome_oficial)
        out_dir = td / "arte"
        t_arte = time.perf_counter()
        completa_impl.gerar_arte(
            nome_oficial,
            uf,
            str(map_b),
            str(map_p),
            out_dir,
            n_arq,
            prefix=prefix,
            nome_exibicao=nome_exibir,
            somente_variante=cor,
            centroide_geo=r.get("centroide_geo"),
        )
        ms_gerar_arte = int((time.perf_counter() - t_arte) * 1000)
        log.info(
            "completa_timing pintar_municipio_ms=%s gerar_arte_ms=%s preview=%s dpi=%s",
            ms_pintar,
            ms_gerar_arte,
            preview,
            pintar_dpi,
        )
        suf = "preto" if cor == "preto" else "branco"
        img_path = out_dir / f"{n_arq}_arte_{suf}.png"
        if not img_path.is_file():
            raise FileNotFoundError(f"Arte não gerada: {img_path}")
        img = Image.open(img_path).convert("RGBA")

    if opcoes.get("resolucao") == "preview":
        max_dim = int(os.environ.get("PREVIEW_MAX_DIM", "800"))
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img
