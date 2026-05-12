# Map Engine API

API FastAPI que expõe os **6 estilos** de arte geográfica migrados de `arte-lojas` (ver `estamparia/BRIEFING_MAPENGINE.md`). Cada estilo implementa `gerar(localidades, opcoes) -> PIL.Image`; paths vêm de `ASSETS_DIR` e saídas temporárias de `OUTPUT_DIR`.

## Estrutura

| Caminho | Função |
|---------|--------|
| `api/` | FastAPI, modelos, rotas (`arte`, `batch`, `validar`) |
| `engine/dispatcher.py` | Roteamento por `estilo` |
| `engine/estilos/` | `v1a`, `v1d`, `v1d2`, `v1e`, `v2c`, `completa` |
| `engine/utils/` | `localidade`, `coordenadas`, `contorno`, `pintar_municipio`, `svg_pendentes`, `cache` |
| `engine/pintar.py` | Fachada → `processar_municipio` |
| `engine/compor.py` | Fachada → `completa_impl.gerar_arte` |
| `assets/` | `font/`, `svg_estados/`, `arte-completa/` (montar a partir de `arte-lojas`) |

## Setup local

```bash
cd map-engine
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -r ../arte-lojas/font/* assets/font/
cp -r ../arte-lojas/svg_estados/* assets/svg_estados/
cp .env.example .env
# opcional: apontar para a pasta inteira do arte-lojas
# export ASSETS_DIR=/caminho/para/arte-lojas
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/health` | `ok`, `assets_ok`, `ibge_ok` |
| POST | `/arte` | JSON `ArteRequest` → PNG |
| POST | `/arte/preview` | força `resolucao=preview` |
| GET | `/localidade/buscar?q=` | autocomplete IBGE + Nominatim |
| GET | `/estilos` | lista dos 6 estilos |
| GET | `/arte/status` | stub de métricas |
| GET | `/validar/{uf}` | checa `UF_branco.svg` e `UF_preto.svg` |
| POST | `/batch/estado/{uf}` | gera PNGs em `OUTPUT_DIR/batch/{UF}/{run_id}/` — exige `X-API-Key` = `API_KEY` |

### Batch

Corpo (`BatchEstadoBody`): `estilos`, `municipios` (`["todos"]` ou nomes), `texto_linha1`, `texto_legenda`, `posicao`, `cor`, `resolucao`.

Limite de municípios: `BATCH_MAX_MUNICIPIOS` (padrão 40).

## Docker

```bash
docker build -t map-engine .
docker run -p 8000:8000 -e ASSETS_DIR=/app/assets -v "$(pwd)/assets:/app/assets" map-engine
```

## Próximos passos (opcional)

- Métricas reais em `/arte/status` e rate limits por plano.
- Fila assíncrona (Redis/RQ) se o batch precisar de centenas de municípios por request.
