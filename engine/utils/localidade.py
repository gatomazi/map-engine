"""
Resolve free-text localities to {municipio, uf} for the map engine.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx
import requests

from engine.utils.localidade_exceptions import LocalidadeNaoEncontrada


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _tentar_parse_direto(texto: str) -> dict | None:
    """Tenta extrair 'Cidade, UF' do texto."""
    match = re.match(r"^(.+?),?\s+([A-Za-z]{2})$", texto.strip())
    if match:
        return {"municipio": match.group(1).strip(), "uf": match.group(2).upper()}
    return None


_municipios_ibge_cache: list[dict] | None = None


def _lista_municipios_ibge() -> list[dict]:
    global _municipios_ibge_cache
    if _municipios_ibge_cache is not None:
        return _municipios_ibge_cache
    r = requests.get(
        "https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
        timeout=60,
    )
    r.raise_for_status()
    _municipios_ibge_cache = r.json()
    return _municipios_ibge_cache


def _buscar_ibge(texto: str) -> dict | None:
    """
    Busca município por nome em todos os estados (API IBGE, cache em memória).
    """
    nome_busca = texto.strip()
    if "," in nome_busca:
        partes = nome_busca.rsplit(",", 1)
        nome_busca = partes[0].strip()
    alvo = _norm(nome_busca)
    if not alvo:
        return None
    try:
        for m in _lista_municipios_ibge():
            if _norm(m.get("nome", "")) == alvo:
                microrregiao = m.get("microrregiao") or {}
                meso = microrregiao.get("mesorregiao") or {}
                uf_obj = meso.get("UF") or {}
                sigla = uf_obj.get("sigla")
                if sigla:
                    return {"municipio": m["nome"], "uf": sigla}
    except Exception:
        return None
    return None


def _buscar_nominatim(texto: str) -> dict | None:
    """Fallback OSM Nominatim (requer User-Agent identificável)."""
    try:
        with httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "map-engine/1.0 (localidade resolver)"},
        ) as client:
            r = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": texto,
                    "format": "json",
                    "limit": 3,
                    "countrycodes": "br",
                    "addressdetails": 1,
                },
            )
        if r.status_code != 200:
            return None
        data: list[dict[str, Any]] = r.json()
        for item in data:
            addr = item.get("address") or {}
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or addr.get("suburb")
                or addr.get("quarter")
            )
            state = addr.get("ISO3166-2-lvl4")  # e.g. BR-SC
            if state and isinstance(state, str) and state.startswith("BR-"):
                uf = state[3:5].upper()
                if city:
                    return {"municipio": city, "uf": uf}
    except Exception:
        return None
    return None


def resolver_localidades(textos: list[str]) -> list[dict]:
    """
    Converte lista de strings livres em lista de dicts com municipio + uf.
    Ordem: parse direto → IBGE → Nominatim.
    """
    resultado: list[dict] = []
    for texto in textos:
        resolvido = _tentar_parse_direto(texto)
        if not resolvido:
            resolvido = _buscar_ibge(texto)
        if not resolvido:
            resolvido = _buscar_nominatim(texto)
        if not resolvido:
            raise LocalidadeNaoEncontrada(f"Não encontrei: '{texto}'")
        resultado.append(resolvido)
    return resultado


def buscar_ibge_e_osm(q: str, limit: int = 10) -> list[dict]:
    """
    Resultados para autocomplete: municípios IBGE cujo nome contém q,
    limitado a `limit` itens.
    """
    qn = _norm(q)
    if len(qn) < 2:
        return []
    out: list[dict] = []
    try:
        for m in _lista_municipios_ibge():
            if qn in _norm(m.get("nome", "")):
                microrregiao = m.get("microrregiao") or {}
                meso = microrregiao.get("mesorregiao") or {}
                uf_obj = meso.get("UF") or {}
                sigla = uf_obj.get("sigla")
                if sigla:
                    out.append(
                        {
                            "nome": m["nome"],
                            "uf": sigla,
                            "tipo": "municipio",
                        }
                    )
                if len(out) >= limit:
                    break
    except Exception:
        return []
    return out
