"""
Fachada da arte estilo «completa» (mapa + tipografia + linha).

A implementação está em `engine.estilos.completa_impl`; a API usa `engine.estilos.completa.gerar`.
"""

from __future__ import annotations

from engine.estilos.completa_impl import gerar_arte, nome_arquivo

__all__ = ["gerar_arte", "nome_arquivo"]
