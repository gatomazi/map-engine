"""Pinta um município no SVG já parseado (lxml tree) — usado por V1-A, V1-D, etc."""

from __future__ import annotations

import re
from pathlib import Path

import requests

from engine.utils import svg_pendentes as _sp


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def pintar_municipio_no_tree(
    tree,
    uf: str,
    nome_cidade: str,
    mun_fill: str,
    pasta_svg: Path,
) -> None:
    svg_path = pasta_svg / f"{uf}_branco.svg"
    muns = requests.get(
        f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
        timeout=20,
    ).json()
    codigo = next(
        (m["id"] for m in muns if _norm(m["nome"]) == _norm(nome_cidade)), None
    )
    if not codigo:
        raise ValueError(f"Município não encontrado no IBGE: {nome_cidade}/{uf}")

    gj = requests.get(
        f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}"
        "?formato=application/vnd.geo+json&qualidade=minima",
        timeout=20,
    ).json()
    bounds_mun = _sp.calcular_bounds_coords(_sp.extrair_todas_coordenadas(gj))
    bounds_est = _sp.baixar_bounds_estado(uf)
    bounds_svg, paths_info = _sp.preprocessar_svg(svg_path)

    if not (bounds_mun and bounds_est and bounds_svg and paths_info):
        raise ValueError("Bounds incompletos")

    bounds_mun_svg = _sp.calcular_bounds_municipio_em_svg(
        bounds_mun, bounds_est, bounds_svg
    )
    melhor = _sp.encontrar_melhor_path(paths_info, bounds_mun_svg, nome_cidade)
    if not melhor:
        raise ValueError("Path do município não encontrado no SVG")

    path_el = None
    if melhor.get("elem_id"):
        for e in tree.iter():
            if e.get("id") == melhor["elem_id"]:
                path_el = e
                break
    if path_el is None and melhor.get("d_prefix"):
        for e in tree.iter():
            if e.get("d", "").startswith(melhor["d_prefix"]):
                path_el = e
                break

    if path_el is None:
        raise ValueError("Elemento SVG não re-localizado")

    style = path_el.get("style", "")
    style = re.sub(r"fill:[^;]+", f"fill:{mun_fill}", style)
    if "fill:" not in style:
        style += f";fill:{mun_fill}"
    style = re.sub(r"fill-opacity:[^;]+", "fill-opacity:1", style)
    if "fill-opacity:" not in style:
        style += ";fill-opacity:1"
    path_el.set("style", style)
