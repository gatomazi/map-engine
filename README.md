# Map Engine API

API FastAPI que expõe os estilos de arte geográfica (ver `estamparia/BRIEFING_MAPENGINE.md` no repo irmão). Este repositório está **escalado**: estrutura, endpoints, `coordenadas`/`contorno` vindos de `arte-lojas`, e **placeholders PNG** nos seis estilos até migrar `gerar_arte_*.py`.

## Estrutura

- `api/` — FastAPI, modelos Pydantic, rotas
- `engine/` — dispatcher, estilos (stub), `pintar`/`compor` (TODO), `utils/`
- `assets/font` e `assets/svg_estados` — copiar de `arte-lojas`

## Setup local

```bash
cd map-engine
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -r ../arte-lojas/font/* assets/font/
cp -r ../arte-lojas/svg_estados/* assets/svg_estados/
cp .env.example .env
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints principais

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/health` | `ok`, `assets_ok`, `ibge_ok` |
| POST | `/arte` | JSON `ArteRequest` → PNG |
| POST | `/arte/preview` | força `resolucao=preview` |
| GET | `/localidade/buscar?q=` | autocomplete IBGE |
| GET | `/estilos` | lista de estilos |
| GET | `/arte/status` | stub de métricas |
| GET | `/validar/{uf}` | checa SVGs em `assets/svg_estados` |
| POST | `/batch/estado/{uf}` | exige `API_KEY` no header `X-API-Key` |

## Próximos passos

1. Substituir `engine/estilos/*.py` pela lógica real de `arte-lojas/gerar_arte_*.py` (`gerar(localidades, opcoes) -> PIL.Image`, paths via `ASSETS_DIR`).
2. Implementar `engine/pintar.py` e `engine/compor.py` a partir dos scripts originais.
3. Ajustar CORS e rate limits para produção.

## Docker

```bash
docker build -t map-engine .
docker run -p 8000:8000 -e ASSETS_DIR=/app/assets -v "$(pwd)/assets:/app/assets" map-engine
```
