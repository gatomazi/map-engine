from __future__ import annotations

from engine.estilos import completa, v1a, v1d, v1d2, v1e, v2c

ESTILOS = {
    "v1a": v1a.gerar,
    "v1d": v1d.gerar,
    "v1d2": v1d2.gerar,
    "v1e": v1e.gerar,
    "v2c": v2c.gerar,
    "completa": completa.gerar,
}


def gerar(
    localidades: list[dict],
    texto_linha1: str,
    texto_linha2: str,
    texto_legenda: str | None,
    posicao: str,
    estilo: str,
    cor: str,
    resolucao: str,
):
    fn = ESTILOS.get(estilo)
    if not fn:
        raise ValueError(f"Estilo desconhecido: {estilo}")

    opcoes = {
        "texto_linha1": texto_linha1,
        "texto_linha2": texto_linha2,
        "texto_legenda": texto_legenda,
        "posicao": posicao,
        "cor": cor,
        "resolucao": resolucao,
    }

    return fn(localidades, opcoes)
