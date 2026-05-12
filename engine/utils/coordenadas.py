#!/usr/bin/env python3
"""
Buscar Coordenadas de Municípios - IBGE
---------------------------------------
Este programa:
1. Acessa a API do IBGE para buscar latitude e longitude de um município
2. Converte as coordenadas para o formato G°M′ · G°M′
"""

import re
import os
import zipfile
import tempfile
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

# Configurações (OUTPUT_DIR via env — Map Engine / Railway)
_ROOT = Path(__file__).resolve().parent.parent.parent
_OUTPUT = Path(os.environ.get("OUTPUT_DIR", str(_ROOT / ".data" / "output")))
_OUTPUT.mkdir(parents=True, exist_ok=True)
PASTA_SAIDA = _OUTPUT / "saida"
PASTA_SAIDA.mkdir(exist_ok=True)

# Cache do arquivo KML do IBGE
PASTA_CACHE = _OUTPUT / ".cache"
PASTA_CACHE.mkdir(parents=True, exist_ok=True)
ARQUIVO_KML_ZIP = PASTA_CACHE / "Localidades_Municipios_kml.zip"
URL_KML_IBGE = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/Localidades_Municipios_kml.zip"


def normalizar_nome(nome):
    """Normaliza o nome para comparação (sem acentos, minúsculas)."""
    import unicodedata
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.lower().strip().replace('-', ' ')


def buscar_codigo_ibge(uf, cidade):
    """Busca o código IBGE do município."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            municipios = response.json()
            cidade_norm = normalizar_nome(cidade)
            
            for m in municipios:
                if normalizar_nome(m["nome"]) == cidade_norm:
                    return m["id"], m["nome"]
    except Exception as e:
        print(f"   ⚠️ Erro ao buscar código: {e}")
    
    return None, None


def baixar_kml_ibge():
    """
    Baixa o arquivo ZIP com os KMLs das localidades do IBGE (se não existir em cache).
    """
    if ARQUIVO_KML_ZIP.exists():
        return True
    
    print(f"   📥 Baixando base de coordenadas do IBGE (primeira execução)...")
    
    try:
        response = requests.get(URL_KML_IBGE, timeout=120, stream=True)
        if response.status_code == 200:
            with open(ARQUIVO_KML_ZIP, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"   ✅ Base baixada e armazenada em cache")
            return True
    except Exception as e:
        print(f"   ⚠️ Erro ao baixar base KML: {e}")
    
    return False


def extrair_coordenadas_kml(codigo, uf, nome_cidade):
    """
    Extrai as coordenadas da sede do município a partir do arquivo KML do IBGE.
    
    Args:
        codigo: Código IBGE do município (7 dígitos)
        uf: Sigla do estado
        nome_cidade: Nome da cidade
    
    Returns:
        tuple: (latitude, longitude) ou (None, None) se não encontrar
    """
    if not ARQUIVO_KML_ZIP.exists():
        return None, None
    
    # Normaliza o nome do município para encontrar o arquivo
    import unicodedata
    nome_norm = unicodedata.normalize('NFKD', nome_cidade)
    nome_norm = ''.join(c for c in nome_norm if not unicodedata.combining(c))
    nome_norm = nome_norm.lower().strip()
    nome_norm = re.sub(r'\s+', '_', nome_norm)
    nome_norm = re.sub(r'[^a-z0-9_]', '', nome_norm)
    
    # Nome do arquivo KML esperado
    arquivo_kml = f"kml/{uf.upper()}/{nome_norm}_{codigo}_localidades_2022.kml"
    
    try:
        with zipfile.ZipFile(ARQUIVO_KML_ZIP, 'r') as zf:
            # Lista arquivos para encontrar o correto (pode ter variações no nome)
            arquivos_uf = [f for f in zf.namelist() if f.startswith(f"kml/{uf.upper()}/") and str(codigo) in f]
            
            if not arquivos_uf:
                return None, None
            
            arquivo_kml = arquivos_uf[0]
            
            with zf.open(arquivo_kml) as kml_file:
                tree = ET.parse(kml_file)
                root = tree.getroot()
                ns = {'kml': 'http://www.opengis.net/kml/2.2'}
                
                # Procura o folder "01. Cidade" que contém a sede
                for folder in root.iter('{http://www.opengis.net/kml/2.2}Folder'):
                    folder_name = folder.find('kml:name', ns)
                    if folder_name is not None and 'Cidade' in folder_name.text:
                        # Pega o primeiro Placemark dentro do folder Cidade
                        for placemark in folder.iter('{http://www.opengis.net/kml/2.2}Placemark'):
                            coords = placemark.find('.//kml:coordinates', ns)
                            if coords is not None:
                                coord_text = coords.text.strip()
                                # Formato KML: longitude,latitude,altitude
                                parts = coord_text.split(',')
                                if len(parts) >= 2:
                                    longitude = float(parts[0])
                                    latitude = float(parts[1])
                                    return latitude, longitude
                        break
                        
    except Exception as e:
        print(f"   ⚠️ Erro ao extrair coordenadas do KML: {e}")
    
    return None, None


def buscar_coordenadas_ibge(codigo, uf, nome_cidade):
    """
    Busca as coordenadas (latitude e longitude) da SEDE do município.
    
    Fontes (em ordem de prioridade):
    1. Arquivo KML oficial do IBGE (coordenadas exatas da sede)
    2. OpenStreetMap Nominatim (fallback)
    3. Centróide do GeoJSON do IBGE (último recurso)
    
    Args:
        codigo: Código IBGE do município (7 dígitos)
        uf: Sigla do estado
        nome_cidade: Nome da cidade
    
    Returns:
        tuple: (latitude, longitude) ou (None, None) se não encontrar
    """
    # 1. Tenta baixar/usar o arquivo KML do IBGE
    if baixar_kml_ibge():
        latitude, longitude = extrair_coordenadas_kml(codigo, uf, nome_cidade)
        if latitude is not None and longitude is not None:
            return latitude, longitude
        print(f"   ⚠️ Município não encontrado no KML, tentando alternativas...")
    
    # 2. Fallback: OpenStreetMap Nominatim
    estados = {
        'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas',
        'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo',
        'GO': 'Goiás', 'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul',
        'MG': 'Minas Gerais', 'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná',
        'PE': 'Pernambuco', 'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
        'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina',
        'SP': 'São Paulo', 'SE': 'Sergipe', 'TO': 'Tocantins'
    }
    
    nome_estado = estados.get(uf.upper(), uf)
    query = f"{nome_cidade}, {nome_estado}, Brazil"
    url = f"https://nominatim.openstreetmap.org/search?q={quote(query)}&format=json&limit=1"
    
    try:
        headers = {'User-Agent': 'IBGE-Municipios-Coords/1.0'}
        response = requests.get(url, timeout=30, headers=headers)
        
        if response.status_code == 200:
            dados = response.json()
            if dados and len(dados) > 0:
                print(f"   ⚠️ Usando coordenadas do OpenStreetMap")
                return float(dados[0]['lat']), float(dados[0]['lon'])
    except Exception as e:
        print(f"   ⚠️ Erro ao buscar via Nominatim: {e}")
    
    # 3. Último recurso: centróide do GeoJSON
    print(f"   ⚠️ Usando centróide do polígono IBGE como fallback...")
    return buscar_coordenadas_geojson(codigo)


def buscar_coordenadas_geojson(codigo):
    """
    Busca as coordenadas calculando o centróide do GeoJSON (fallback).
    
    Args:
        codigo: Código IBGE do município (7 dígitos)
    
    Returns:
        tuple: (latitude, longitude) ou (None, None) se não encontrar
    """
    url = f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}?formato=application/vnd.geo+json"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            geojson = response.json()
            coords = extrair_todas_coordenadas(geojson)
            
            if coords:
                sum_lon = sum(c[0] for c in coords)
                sum_lat = sum(c[1] for c in coords)
                n = len(coords)
                
                longitude = sum_lon / n
                latitude = sum_lat / n
                
                return latitude, longitude
    except Exception as e:
        print(f"   ⚠️ Erro ao buscar GeoJSON: {e}")
    
    return None, None


def extrair_todas_coordenadas(geojson):
    """Extrai todas as coordenadas de um GeoJSON."""
    coords = []
    
    def extrair(obj):
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                coords.append((obj[0], obj[1]))
            else:
                for item in obj:
                    extrair(item)
        elif isinstance(obj, dict):
            if "coordinates" in obj:
                extrair(obj["coordinates"])
            elif "geometry" in obj:
                extrair(obj["geometry"])
            elif "features" in obj:
                for f in obj["features"]:
                    extrair(f)
    
    extrair(geojson)
    return coords


def converter_decimal_para_graus_minutos(valor_decimal):
    """
    Converte coordenada decimal para graus e minutos.
    
    Passos:
    1. Ignora o sinal negativo (usa valor absoluto)
    2. Parte inteira = graus
    3. Parte decimal × 60 = minutos
    4. Arredonda minutos para inteiro mais próximo
    
    Args:
        valor_decimal: Coordenada em formato decimal (ex: -22.793)
    
    Returns:
        tuple: (graus, minutos) como inteiros
    """
    # 1. Ignora o sinal negativo
    valor_abs = abs(valor_decimal)
    
    # 2. Identifica os graus (parte inteira)
    graus = int(valor_abs)
    
    # 3. Subtrai os graus do valor total
    parte_decimal = valor_abs - graus
    
    # 4. Converte a parte decimal em minutos (× 60)
    minutos_decimal = parte_decimal * 60
    
    # 5. Arredonda os minutos para o inteiro mais próximo
    minutos = round(minutos_decimal)
    
    # Se arredondar para 60, incrementa grau
    if minutos == 60:
        graus += 1
        minutos = 0
    
    return graus, minutos


def formatar_coordenadas(latitude, longitude):
    """
    Formata latitude e longitude no padrão G°M′ · G°M′
    
    Args:
        latitude: Latitude em decimal (ex: -22.793)
        longitude: Longitude em decimal (ex: -51.716)
    
    Returns:
        str: Coordenadas formatadas (ex: "22°48′ · 51°43′")
    """
    lat_graus, lat_minutos = converter_decimal_para_graus_minutos(latitude)
    lon_graus, lon_minutos = converter_decimal_para_graus_minutos(longitude)
    
    return f"{lat_graus}°{lat_minutos:02d}′ · {lon_graus}°{lon_minutos:02d}′"


def buscar_e_formatar_coordenadas(uf, cidade):
    """
    Busca as coordenadas de um município no IBGE e formata no padrão G°M′ · G°M′
    
    Args:
        uf: Sigla do estado (ex: PR, SC, RS)
        cidade: Nome da cidade
    
    Returns:
        dict: Dicionário com informações do município e coordenadas formatadas
    """
    print(f"\n{'='*60}")
    print(f"📍 Buscando coordenadas: {cidade}/{uf}")
    print(f"{'='*60}")
    
    # 1. Busca código IBGE
    print(f"\n   🔍 Buscando código IBGE...")
    codigo, nome_oficial = buscar_codigo_ibge(uf, cidade)
    
    if not codigo:
        print(f"   ❌ Município '{cidade}' não encontrado em {uf}")
        return None
    
    print(f"   ✅ Código: {codigo} - {nome_oficial}")
    
    # 2. Busca coordenadas da sede do município
    print(f"\n   📥 Buscando coordenadas da sede...")
    latitude, longitude = buscar_coordenadas_ibge(codigo, uf, nome_oficial)
    
    if latitude is None or longitude is None:
        print(f"   ❌ Não foi possível obter coordenadas do município")
        return None
    
    print(f"   ✅ Latitude:  {latitude:.3f}")
    print(f"   ✅ Longitude: {longitude:.3f}")
    
    # 3. Converte para graus e minutos
    print(f"\n   🔄 Convertendo para graus e minutos...")
    
    lat_graus, lat_minutos = converter_decimal_para_graus_minutos(latitude)
    lon_graus, lon_minutos = converter_decimal_para_graus_minutos(longitude)
    
    print(f"   ✅ Latitude:  {lat_graus}° {lat_minutos:02d}′")
    print(f"   ✅ Longitude: {lon_graus}° {lon_minutos:02d}′")
    
    # 4. Formata no padrão final
    coordenadas_formatadas = formatar_coordenadas(latitude, longitude)
    
    print(f"\n   {'='*40}")
    print(f"   📌 RESULTADO FINAL: {coordenadas_formatadas}")
    print(f"   {'='*40}")
    
    return {
        "municipio": nome_oficial,
        "codigo": codigo,
        "uf": uf.upper(),
        "latitude_decimal": latitude,
        "longitude_decimal": longitude,
        "latitude_graus": lat_graus,
        "latitude_minutos": lat_minutos,
        "longitude_graus": lon_graus,
        "longitude_minutos": lon_minutos,
        "coordenadas_formatadas": coordenadas_formatadas
    }


def carregar_municipios_arquivo(arquivo):
    """Carrega lista de municípios de um arquivo."""
    municipios = []
    
    try:
        with open(arquivo, 'r', encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                # Ignora linhas vazias e comentários
                if not linha or linha.startswith('#'):
                    continue
                municipios.append(linha)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {arquivo}")
    except Exception as e:
        print(f"❌ Erro ao ler arquivo: {e}")
    
    return municipios


def main():
    """Função principal."""
    import argparse
    
    # Arquivo padrão de municípios
    arquivo_padrao = _OUTPUT / "municipios.txt"
    
    parser = argparse.ArgumentParser(
        description="Buscar Coordenadas de Municípios - IBGE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Exemplos:
  # Processar municípios do arquivo padrão (municipios.txt)
  python coordenadas.py
  
  # Processar municípios de outro arquivo
  python coordenadas.py -a minha_lista.txt
  
  # Processar municípios específicos
  python coordenadas.py "Toledo,PR" "Joinville,SC"

Arquivo de entrada ({arquivo_padrao}):
  - Um município por linha no formato: Cidade,UF
  - Linhas começando com # são comentários
  - Linhas em branco são ignoradas

Formato de saída:
  As coordenadas são convertidas de decimal para graus e minutos:
  
  Exemplo:
    Latitude:  -22.793 → 22°48′
    Longitude: -51.716 → 51°43′
    
    Resultado: 22°48′ · 51°43′
        """
    )
    
    parser.add_argument("municipios", nargs="*", 
                        help="Municípios no formato 'Cidade,UF' (ex: 'Toledo,PR')")
    parser.add_argument("-a", "--arquivo", type=str, default=None,
                        help=f"Arquivo com lista de municípios (padrão: {arquivo_padrao})")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("    BUSCAR COORDENADAS DE MUNICÍPIOS - IBGE")
    print("    Formato de saída: G°M′ · G°M′")
    print("=" * 60)
    
    # Determina a lista de municípios
    if args.municipios:
        # Usa municípios passados como argumento
        lista_municipios = args.municipios
        print(f"\n📋 Processando {len(lista_municipios)} município(s) da linha de comando")
    else:
        # Carrega do arquivo
        arquivo = args.arquivo if args.arquivo else arquivo_padrao
        print(f"\n📄 Carregando municípios de: {arquivo}")
        lista_municipios = carregar_municipios_arquivo(arquivo)
        
        if not lista_municipios:
            print(f"\n⚠️ Nenhum município encontrado no arquivo.")
            print(f"   Edite o arquivo {arquivo} e adicione os municípios desejados.")
            print(f"   Formato: Cidade,UF (um por linha)")
            return []
        
        print(f"   📋 {len(lista_municipios)} município(s) encontrado(s)")
    
    resultados = []
    
    for item in lista_municipios:
        if ',' not in item:
            print(f"\n⚠️ Formato inválido: '{item}'. Use 'Cidade,UF'")
            continue
        
        partes = item.rsplit(',', 1)
        cidade = partes[0].strip()
        uf = partes[1].strip().upper()
        
        resultado = buscar_e_formatar_coordenadas(uf, cidade)
        if resultado:
            resultados.append(resultado)
    
    # Resumo final
    print(f"\n{'='*60}")
    print(f"📊 RESUMO DAS COORDENADAS")
    print(f"{'='*60}")
    
    for r in resultados:
        print(f"   {r['municipio']}/{r['uf']}: {r['coordenadas_formatadas']}")
    
    # Salva resultado em arquivo
    if resultados:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_saida = PASTA_SAIDA / f"coordenadas_{timestamp}.txt"
        
        with open(arquivo_saida, 'w', encoding='utf-8') as f:
            for r in resultados:
                f.write(f"{r['municipio']} - {r['coordenadas_formatadas']}\n")
        
        print(f"\n   📄 Arquivo salvo: {arquivo_saida}")
    
    print(f"\n{'='*60}")
    print(f"✅ PROCESSAMENTO CONCLUÍDO!")
    print(f"   Sucessos: {len(resultados)}/{len(lista_municipios)}")
    print(f"{'='*60}")
    
    return resultados


if __name__ == "__main__":
    main()
