from typing import Literal, Optional

from pydantic import BaseModel, Field


class ArteRequest(BaseModel):
    localidades: list[str] = Field(..., min_length=1)
    texto_linha1: str = "LÁ DE"
    texto_linha2: str = Field(..., min_length=1)
    texto_legenda: Optional[str] = None
    posicao: Literal["top", "center", "bottom"] = "center"
    estilo: Literal["completa", "v1a", "v1d", "v1d2", "v1e", "v2c"] = "completa"
    cor: Literal["preto", "branco"] = "preto"
    resolucao: Literal["preview", "final"] = "preview"


class BatchEstadoBody(BaseModel):
    estilos: list[str] = Field(default_factory=lambda: ["v1d"])
    municipios: list[str] = Field(
        default_factory=lambda: ["todos"],
        description='Use ["todos"] ou lista de nomes de municípios',
    )
    texto_linha1: str = "LÁ DE"
    texto_legenda: Optional[str] = None
    posicao: Literal["top", "center", "bottom"] = "center"
    cor: Literal["preto", "branco"] = "preto"
    resolucao: Literal["preview", "final"] = "preview"
