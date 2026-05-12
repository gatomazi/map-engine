from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image

from engine.estilos import completa_impl
from engine.utils.pintar_municipio import processar_municipio


def gerar(localidades: list[dict], opcoes: dict | None = None) -> Image.Image:
    opcoes = opcoes or {}
    if not localidades:
        raise ValueError("localidades vazia")
    loc = localidades[0]
    uf = loc["uf"].strip().upper()
    nome_ibge = loc["municipio"].strip()
    nome_exibir = (opcoes.get("texto_linha2") or nome_ibge).strip()
    prefix = opcoes.get("texto_linha1")

    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        p_maps = td / "maps" / uf
        p_maps.mkdir(parents=True, exist_ok=True)
        r = processar_municipio(nome_ibge, uf, pasta_uf_dest=p_maps)
        if not r or not r.get("arquivos"):
            raise RuntimeError(
                f"Falha ao gerar mapas pintados para {nome_ibge}/{uf} "
                "(verifique ASSETS_DIR/svg_estados e conectividade IBGE)."
            )
        by_cor = {a["cor"]: Path(a["png"]) for a in r["arquivos"] if a}
        map_b = by_cor.get("branco")
        map_p = by_cor.get("preto")
        if not map_b or not map_p or not map_b.is_file() or not map_p.is_file():
            raise RuntimeError(
                f"PNG branco/preto incompleto após pintar: {by_cor!r}"
            )

        nome_oficial = r["municipio"]
        n_arq = completa_impl.nome_arquivo(nome_oficial)
        out_dir = td / "arte"
        completa_impl.gerar_arte(
            nome_oficial,
            uf,
            str(map_b),
            str(map_p),
            out_dir,
            n_arq,
            prefix=prefix,
            nome_exibicao=nome_exibir,
        )
        cor = opcoes.get("cor", "preto")
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
