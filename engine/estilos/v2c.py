#!/usr/bin/env python3
"""
Gerar Arte V2-C
----------------
Estilo: nome da cidade dominante no topo + mapa secundário abaixo + ano de fundação.

  - Fundo escuro #0e0f0b
  - Cidade em Fraunces Black muito grande (topo)
  - Contorno fino do estado + município em gold (mapa menor, centralizado)
  - Abaixo do mapa: sigla UF em Space Grotesk + "est. XXXX" em Fraunces LightItalic

Uso:
  python gerar_arte_v2c.py --cidade "Toledo,PR"
  python gerar_arte_v2c.py --uf PR SC RS
"""

import os
import csv
import io
import re
import sys
import tempfile
import unicodedata
import requests
from pathlib import Path

import cairosvg
import numpy as np
from lxml import etree
from PIL import Image, ImageDraw, ImageFont

def _assets_dir() -> Path:
    return Path(
        os.environ.get(
            "ASSETS_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "assets"),
        )
    )


PASTA_BASE = Path(__file__).resolve().parent.parent.parent
PASTA_SVG = _assets_dir() / "svg_estados"
PASTA_SAIDA = (
    Path(os.environ.get("OUTPUT_DIR", str(PASTA_BASE / ".data" / "output"))) / "v2c_cli"
)
PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
ARQUIVO_CSV = PASTA_BASE / "cidades_pendentes.csv"

CANVAS_W = 4270
CANVAS_H = 4900

# Mapa proporcionalmente menor que V1-D para dar espaço ao texto
UF_CONFIG = {
    'SC': dict(vis_x=373, vis_y=590, vis_w=2660),
    'PR': dict(vis_x=383, vis_y=544, vis_w=2707),
    'RS': dict(vis_x=501, vis_y=575, vis_w=2480),
    'GO': dict(vis_x=625, vis_y=557, vis_w=2272),
    'MS': dict(vis_x=579, vis_y=564, vis_w=2370),
    'MT': dict(vis_x=622, vis_y=550, vis_w=2293),
    'DF': dict(vis_x=700, vis_y=557, vis_w=2175),
    'AC': dict(vis_x=344, vis_y=661, vis_w=2787),
    'AM': dict(vis_x=239, vis_y=665, vis_w=2834),
    'AP': dict(vis_x=758, vis_y=660, vis_w=1946),
    'PA': dict(vis_x=708, vis_y=662, vis_w=2297),
    'RO': dict(vis_x=344, vis_y=669, vis_w=2645),
    'RR': dict(vis_x=741, vis_y=667, vis_w=1968),
    'TO': dict(vis_x=1231, vis_y=664, vis_w=1363),
}
_DEFAULT_CFG = dict(vis_x=373, vis_y=590, vis_w=2660)

BG            = (0, 0, 0, 0)

_PALETAS = {
    'escura': dict(
        outline    = (  0,   0,   0, 255),
        text       = (  0,   0,   0, 255),
        mun_fill   = '#4d543d',
        accent     = ( 77,  84,  61, 255),
        rule       = ( 77,  84,  61, 180),
    ),
    'clara': dict(
        outline    = (255, 255, 255, 255),
        text       = (242, 240, 239, 255),
        mun_fill   = '#d6ba8d',
        accent     = (214, 186, 141, 255),
        rule       = (214, 186, 141, 180),
    ),
}
OUTLINE_PX    = 13

UF_NOMES = {
    'AC': 'Acre',           'AL': 'Alagoas',          'AP': 'Amapá',
    'AM': 'Amazonas',       'BA': 'Bahia',             'CE': 'Ceará',
    'DF': 'Distrito Federal','ES': 'Espírito Santo',   'GO': 'Goiás',
    'MA': 'Maranhão',       'MT': 'Mato Grosso',       'MS': 'Mato Grosso do Sul',
    'MG': 'Minas Gerais',   'PA': 'Pará',              'PB': 'Paraíba',
    'PR': 'Paraná',         'PE': 'Pernambuco',        'PI': 'Piauí',
    'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte','RS': 'Rio Grande do Sul',
    'RO': 'Rondônia',       'RR': 'Roraima',           'SC': 'Santa Catarina',
    'SP': 'São Paulo',      'SE': 'Sergipe',            'TO': 'Tocantins',
}

FONT_FRAUNCES        = _assets_dir() / "font" / "Fraunces" / "static" / "Fraunces_72pt-Black.ttf"
FONT_FRAUNCES_ITALIC = _assets_dir() / "font" / "Fraunces" / "static" / "Fraunces_72pt-LightItalic.ttf"
FONT_GROTESK         = _assets_dir() / "font" / "Space_Grotesk" / "static" / "SpaceGrotesk-Medium.ttf"
FONT_KESONG          = _assets_dir() / "font" / "xiangcui-kesong" / "kesong-latest.ttf"

if not FONT_FRAUNCES.exists():        FONT_FRAUNCES        = FONT_KESONG
if not FONT_FRAUNCES_ITALIC.exists(): FONT_FRAUNCES_ITALIC = FONT_KESONG
if not FONT_GROTESK.exists():         FONT_GROTESK         = FONT_KESONG


# ─── Base local de anos de fundação ──────────────────────────────────────────
_ANOS_FUNDACAO = {
    'PR': {
        'abatia':1947,'adrianopolis':1961,'agudos do sul':1961,'almirante tamandare':1947,
        'altamira do parana':1983,'alto parana':1954,'alto piquiri':1961,'altonia':1961,
        'alvorada do sul':1954,'amaporã':1961,'ampere':1961,'anahy':1990,'andira':1938,
        'angulo':1990,'antonina':1714,'antonio olinto':1961,'apucarana':1944,
        'arapongas':1947,'arapoti':1954,'arapua':1990,'araruna':1954,'araucaria':1890,
        'ariranha do ivai':1990,'assai':1951,'assis chateaubriand':1966,'astorga':1952,
        'atalaia':1954,'balsa nova':1961,'bandeirantes':1934,'barbosa ferraz':1960,
        'barracão':1952,'barra do jacare':1961,'bela vista da caroba':1990,
        'bela vista do parana':1947,'bituruna':1955,'boa esperanca':1960,
        'boa esperanca do iguacu':1990,'boa ventura de sao roque':1990,
        'boa vista da aparecida':1961,'bocaiuva do sul':1961,'bom jesus do sul':1990,
        'bom sucesso':1961,'bom sucesso do sul':1990,'borrazopolis':1961,'braganey':1990,
        'brasilandia do sul':1990,'cafeara':1961,'cafelandia':1961,'cafezal do sul':1990,
        'california':1961,'cambara':1921,'cambe':1947,'cambira':1961,
        'campina da lagoa':1961,'campina do simao':1990,'campina grande do sul':1961,
        'campo bonito':1990,'campo do tenente':1961,'campo largo':1870,
        'campo magro':1990,'campo mourao':1947,'candido de abreu':1954,'candoi':1990,
        'cantagalo':1990,'capanema':1952,'capitao leonidas marques':1961,
        'carambei':1995,'carlopolis':1938,'cascavel':1951,'castro':1789,
        'catanduvas':1961,'centenario do sul':1951,'cerro azul':1876,'ceu azul':1961,
        'chopinzinho':1961,'cianorte':1953,'cidade gaucha':1955,'clevelandia':1892,
        'colombo':1890,'colorado':1954,'congonhinhas':1951,'conselheiro mairinck':1961,
        'contenda':1961,'corbelia':1961,'cornelio procopio':1938,
        'coronel domingos soares':1990,'coronel vivida':1961,'corumbatai do sul':1961,
        'cruz machado':1952,'cruzeiro do iguacu':1990,'cruzeiro do oeste':1951,
        'cruzeiro do sul':1954,'cruzmaltina':1961,'curitiba':1693,'curiuva':1961,
        'diamante do norte':1961,'diamante do sul':1990,"diamante d'oeste":1990,
        'dois vizinhos':1961,'douradina':1961,'doutor camargo':1954,
        'eneas marques':1961,'engenheiro beltrao':1954,'entre rios do oeste':1990,
        'esperanca nova':1990,'espigao alto do iguacu':1990,'farol':1990,'faxinal':1951,
        'fazenda rio grande':1990,'fenix':1961,'fernandes pinheiro':1990,'figueira':1961,
        'flor da serra do sul':1990,'florai':1954,'floresta':1961,'florestopolis':1961,
        'florida':1961,'formosa do oeste':1961,'foz do iguacu':1914,'foz do jordao':1990,
        'francisco alves':1961,'francisco beltrao':1952,'general carneiro':1961,
        'godoy moreira':1990,'goioere':1955,'goioxim':1990,'grandes rios':1961,
        'guaira':1951,'guairaca':1954,'guamiranga':1990,'guapirama':1961,
        'guaporema':1961,'guaraci':1951,'guaraniacu':1961,'guarapuava':1810,
        'guaraquecaba':1947,'guaratuba':1771,'honorio serpa':1990,'ibaiti':1947,
        'ibema':1990,'ibipora':1947,'icaraima':1961,'iguaracu':1954,'iguatu':1990,
        'imbau':1990,'imbituva':1871,'inacio martins':1961,'inaja':1954,
        'indianopolis':1990,'ipiranga':1878,'ipora':1961,'iracema do oeste':1990,
        'irati':1907,'iretama':1961,'itaguaje':1954,'itaipulandia':1990,
        'itambaraca':1951,'itambe':1954,"itapejara d'oeste":1961,'itaperucu':1961,
        'itauna do sul':1954,'ivai':1961,'ivaipora':1961,'ivate':1961,'ivatuba':1961,
        'jaboti':1961,'jacarezinho':1900,'jaguapita':1954,'jaguariaiva':1823,
        'jandaia do sul':1951,'janiopolis':1961,'japira':1961,'japura':1961,
        'jardim alegre':1961,'jardim olinda':1961,'jataizinho':1954,'jesuitas':1990,
        'joaquim tavora':1951,'jundiai do sul':1961,'juranda':1961,'jussara':1961,
        'kalore':1961,'lapa':1769,'laranjal':1990,'laranjeiras do sul':1946,
        'leopolis':1954,'lidianopolis':1990,'lindoeste':1990,'loanda':1954,
        'lobato':1954,'londrina':1934,'luiziana':1961,'lunardelli':1990,
        'lupionopolis':1954,'mallet':1908,'mambore':1954,'mandaguacu':1954,
        'mandaguari':1947,'mandirituba':1961,'manfrinopolis':1990,'mangueirinha':1944,
        'manoel ribas':1954,'marechal candido rondon':1960,'maria helena':1961,
        'marialva':1951,'marilandia do sul':1961,'marilena':1961,'mariluz':1961,
        'maringa':1951,'mariopolis':1961,'maripa':1990,'marmeleiro':1961,
        'marquinho':1990,'marumbi':1961,'matelandia':1961,'matinhos':1990,
        'mato rico':1990,'maua da serra':1990,'medianeira':1960,'mercedes':1990,
        'mirador':1961,'miraselva':1954,'missal':1961,'moreira sales':1961,
        'morretes':1841,'munhoz de melo':1961,'nossa senhora das gracas':1961,
        'nova alianca do ivai':1990,'nova america da colina':1990,'nova aurora':1961,
        'nova cantu':1961,'nova esperanca':1951,'nova esperanca do sudoeste':1990,
        'nova fatima':1954,'nova laranjeiras':1990,'nova londrina':1954,
        'nova olimpia':1961,'nova prata do iguacu':1961,'nova santa barbara':1990,
        'nova santa rosa':1990,'nova tebas':1961,'novo itacolomi':1990,
        'ortigueira':1951,'ourizona':1961,'ouro verde do oeste':1990,'paicandu':1961,
        'palmas':1879,'palmeira':1877,'palmital':1961,'palotina':1960,
        'paraiso do norte':1961,'paranacity':1954,'paranagua':1648,
        'paranapoema':1961,'paranavai':1952,'pato bragado':1990,'pato branco':1952,
        'paula freitas':1961,'paulo frontin':1961,'peabiru':1954,'perobal':1990,
        'perola':1961,"perola d'oeste":1961,'pien':1961,'pinhais':1992,
        'pinhalao':1961,'pinhal de sao bento':1990,'pinhao':1961,'pirai do sul':1877,
        'piraquara':1890,'pitanga':1943,'pitangueiras':1961,'planaltina do parana':1961,
        'planalto':1961,'ponta grossa':1823,'pontal do parana':1995,'porecatu':1947,
        'porto amazonas':1903,'porto barreiro':1990,'porto rico':1961,
        'porto vitoria':1961,'prado ferreira':1990,'pranchita':1961,
        'presidente castelo branco':1961,'primeiro de maio':1961,'prudentopolis':1906,
        'quarto centenario':1990,'quatigua':1961,'quatro barras':1961,
        'quatro pontes':1990,'quedas do iguacu':1961,'querencia do norte':1954,
        'quinta do sol':1961,'quitandinha':1961,'ramilandia':1990,
        'rancho alegre':1961,"rancho alegre d'oeste":1990,'realeza':1961,
        'reboucas':1909,'renascenca':1961,'reserva':1920,'reserva do iguacu':1990,
        'ribeirao claro':1908,'ribeirao do pinhal':1928,'rio azul':1918,
        'rio bom':1961,'rio bonito do iguacu':1990,'rio branco do ivai':1990,
        'rio branco do sul':1947,'rio negro':1870,'rolandia':1944,'roncador':1961,
        'rondon':1961,'rosario do ivai':1990,'sabaudia':1961,'salgado filho':1961,
        'salto do itarare':1961,'salto do lontra':1961,'santa amelia':1961,
        'santa cecilia do pavao':1990,'santa cruz de monte castelo':1961,
        'santa fe':1951,'santa helena':1961,'santa ines':1961,
        'santa isabel do ivai':1961,'santa izabel do oeste':1961,'santa lucia':1990,
        'santa maria do oeste':1990,'santa mariana':1951,'santa monica':1961,
        'santa tereza do oeste':1990,'santa terezinha de itaipu':1982,
        'santana do itarare':1961,'santo antonio da platina':1914,
        'santo antonio do caiva':1961,'santo antonio do paraiso':1961,
        'santo antonio do sudoeste':1961,'santo inacio':1961,
        'sao carlos do ivai':1961,'sao jeronimo da serra':1951,'sao joao':1961,
        'sao joao do caiva':1961,'sao joao do ivai':1961,'sao joao do triunfo':1890,
        "sao jorge d'oeste":1961,'sao jorge do ivai':1961,
        'sao jorge do patrocinio':1990,'sao jose da boa vista':1961,
        'sao jose das palmeiras':1990,'sao jose dos pinhais':1852,
        'sao manoel do parana':1990,'sao mateus do sul':1908,
        'sao miguel do iguacu':1961,'sao pedro do iguacu':1990,
        'sao pedro do ivai':1951,'sao pedro do parana':1961,
        'sao sebastiao da amoreira':1951,'sao tome':1961,'sapopema':1961,
        'sarandi':1981,'saudade do iguacu':1990,'senges':1938,
        'serranopolis do iguacu':1990,'sertaneja':1961,'sertanopolis':1951,
        'siqueira campos':1921,'sulina':1961,'tamarana':1995,'tamboara':1961,
        'tapejara':1961,'tapira':1961,'teixeira soares':1917,'telemaco borba':1964,
        'terra boa':1954,'terra rica':1954,'terra roxa':1961,'tibagi':1872,
        'tijucas do sul':1951,'toledo':1952,'tomazina':1860,
        'tres barras do parana':1961,'tunas do parana':1990,'tuneiras do oeste':1961,
        'tupassi':1961,'turvo':1982,'ubirata':1961,'umuarama':1955,
        'uniao da vitoria':1890,'uniflor':1961,'urai':1947,'ventania':1990,
        'vera cruz do oeste':1961,'vere':1961,'virmond':1990,'vitorino':1961,
        'wenceslau braz':1938,'xambre':1961,
    },
    'SC': {
        'abdon batista':1962,'abelardo luz':1958,'agrolandia':1962,'agronomica':1962,
        'agua doce':1958,'aguas de chapeco':1962,'aguas frias':1995,'aguas mornas':1961,
        'alfredo wagner':1961,'alto bela vista':1995,'anchieta':1963,'angelina':1961,
        'anita garibaldi':1961,'anitapolis':1961,'antonio carlos':1961,'apiuna':1989,
        'arabuta':1991,'araquari':1876,'ararangua':1880,'armazem':1958,
        'arroio trinta':1963,'arvoredo':1991,'ascurra':1963,'atalanta':1964,
        'aurora':1964,'balneario arroio do silva':1995,'balneario barra do sul':1995,'balneario camboriu':1964,
        'balneario gaivota':1995,'bandeirante':1995,'barra bonita':1995,'barra velha':1961,
        'bela vista do toldo':1995,'belmonte':1995,'benedito novo':1961,'biguacu':1833,
        'blumenau':1880,'bocaina do sul':1995,'bom jardim da serra':1962,'bom jesus':1995,
        'bom jesus do oeste':1995,'bom retiro':1892,'bombinhas':1992,'botuvera':1962,
        'braco do norte':1955,'braco do trombudo':1995,'brunopolis':1995,'brusque':1860,
        'cacador':1934,'caibi':1961,'calmon':1962,'camboriu':1884,
        'campo alegre':1897,'campo belo do sul':1961,'campo ere':1963,'campos novos':1881,
        'canelinha':1961,'canoinhas':1911,'capao alto':1995,'capinzal':1949,
        'capivari de baixo':1992,'catanduvas':1963,'caxambu do sul':1963,'celso ramos':1995,
        'cerro negro':1995,'chapadao do lageado':1995,'chapeco':1917,'cocal do sul':1992,
        'concordia':1934,'cordilheira alta':1995,'coronel freitas':1961,'coronel martins':1995,
        'correia pinto':1982,'corupa':1958,'criciuma':1925,'cunha pora':1961,
        'cunhatai':1995,'curitibanos':1869,'descanso':1963,'dionisio cerqueira':1953,
        'dona emma':1962,'doutor pedrinho':1989,'entre rios':1995,'ermo':1995,
        'erval velho':1961,'faxinal dos guedes':1961,'flor do sertao':1995,'florianopolis':1726,
        'formosa do sul':1995,'forquilhinha':1989,'fraiburgo':1961,'frei rogerio':1995,
        'galvao':1963,'garopaba':1961,'garuva':1963,'gaspar':1934,
        'governador celso ramos':1963,'grao-para':1958,'gravatal':1961,'guabiruba':1962,
        'guaraciaba':1961,'guaramirim':1949,'guaruja do sul':1963,'guatambu':1995,
        "herval d'oeste":1953,'ibiam':1995,'ibicare':1961,'ibirama':1934,
        'icara':1961,'ilhota':1958,'imarui':1890,'imbituba':1958,
        'imbuia':1962,'indaial':1934,'iomere':1995,'ipira':1964,
        'ipora do oeste':1989,'ipuacu':1995,'ipumirim':1963,'iraceminha':1995,
        'irani':1961,'irati':1995,'irineopolis':1961,'ita':1956,
        'itaiopolis':1915,'itajai':1860,'itapema':1962,'itapiranga':1954,
        'itapoa':1989,'ituporanga':1948,'jabora':1961,'jacinto machado':1958,
        'jaguaruna':1961,'jaragua do sul':1934,'jardinopolis':1995,'joacaba':1917,
        'joinville':1851,'jose boiteux':1986,'jupia':1995,'lacerdopolis':1963,
        'lages':1766,'laguna':1676,'lajeado grande':1995,'laurentino':1962,
        'lauro muller':1956,'lebon regis':1958,'leoberto leal':1961,'lindoia do sul':1990,
        'lontras':1961,'luiz alves':1958,'luzerna':1995,'macieira':1995,
        'mafra':1917,'major gercino':1961,'major vieira':1961,'maracaja':1995,
        'maravilha':1958,'marema':1995,'massaranduba':1961,'matos costa':1962,
        'meleiro':1961,'mirim doce':1995,'modelo':1961,'mondai':1961,
        'monte carlo':1995,'monte castelo':1962,'morro da fumaca':1992,'morro grande':1995,
        'navegantes':1962,'nova erechim':1995,'nova itaberaba':1995,'nova trento':1892,
        'nova veneza':1958,'novo horizonte':1995,'orleans':1913,'otacilio costa':1982,
        'ouro':1963,'ouro verde':1995,'paial':1995,'painel':1995,
        'palhoca':1894,'palma sola':1963,'palmeira':1995,'palmitos':1954,
        'papanduva':1953,'paraiso':1995,'passo de torres':1995,'passos maia':1961,
        'paulo lopes':1961,'pedras grandes':1961,'penha':1958,'peritiba':1963,
        'pescaria brava':2013,'petrolandia':1962,'balneario picarras':1963,'pinhalzinho':1961,
        'pinheiro preto':1962,'piratuba':1949,'planalto alegre':1995,'pomerode':1959,
        'ponte alta':1961,'ponte alta do norte':1962,'ponte serrada':1958,'porto belo':1832,
        'porto uniao':1917,'pouso redondo':1958,'praia grande':1958,'presidente castello branco':1963,
        'presidente getulio':1963,'presidente nereu':1963,'princesa':1995,'quilombo':1961,
        'rancho queimado':1961,'rio das antas':1958,'rio do campo':1962,'rio do oeste':1962,
        'rio do sul':1931,'rio dos cedros':1934,'rio fortuna':1958,'rio negrinho':1953,
        'rio rufino':1995,'riqueza':1995,'rodeio':1934,'romelandia':1995,
        'salete':1962,'saltinho':1995,'salto veloso':1962,'sangao':1992,
        'santa cecilia':1958,'santa helena':1995,'santa rosa de lima':1961,'santa rosa do sul':1961,
        'santa terezinha':1962,'santa terezinha do progresso':1995,'santiago do sul':1995,'santo amaro da imperatriz':1958,
        'sao bento do sul':1873,'sao bernardino':1995,'sao bonifacio':1962,'sao carlos':1961,
        'sao cristovao do sul':1995,'sao domingos':1963,'sao francisco do sul':1660,'sao joao batista':1958,
        'sao joao do itaperiu':1995,'sao joao do oeste':1995,'sao joao do sul':1961,'sao joaquim':1887,
        'sao jose':1750,'sao jose do cedro':1963,'sao jose do cerrito':1956,'sao lourenco do oeste':1958,
        'sao ludgero':1961,'sao martinho':1961,'sao miguel da boa vista':1995,'sao miguel do oeste':1953,
        'sao pedro de alcantara':1995,'saudades':1961,'schroeder':1964,'seara':1954,
        'serra alta':1995,'sideropolis':1958,'sombrio':1953,'sul brasil':1995,
        'taio':1962,'tangara':1948,'tigrinhos':1995,'tijucas':1860,
        'timbe do sul':1961,'timbo':1934,'timbo grande':1995,'tres barras':1961,
        'treviso':1995,'treze de maio':1961,'treze tilias':1963,'trombudo central':1962,
        'tubarao':1870,'tunapolis':1995,'turvo':1948,'uniao do oeste':1995,
        'urubici':1956,'urupema':1995,'urussanga':1878,'vargeao':1961,
        'vargem':1995,'vargem bonita':1995,'vidal ramos':1964,'videira':1944,
        'vitor meireles':1962,'witmarsum':1962,'xanxere':1953,'xavantina':1963,
        'xaxim':1953,'zortea':1995,
    },
    'RS': {
        'acegua':1996,'agua santa':1987,'agudo':1959,'ajuricaba':1966,
        'alecrim':1963,'alegrete':1831,'alegria':1987,'almirante tamandare do sul':1992,
        'alpestre':1964,'alto alegre':1988,'alto feliz':1992,'alvorada':1965,
        'amaral ferrador':1988,'ametista do sul':1992,'andre da rocha':1988,'anta gorda':1963,
        'antonio prado':1899,'arambare':1992,'ararica':1992,'aratiba':1955,
        'arroio do meio':1934,'arroio do padre':1996,'arroio do sal':1988,'arroio do tigre':1963,
        'arroio dos ratos':1964,'arroio grande':1873,'arvorezinha':1959,'augusto pestana':1966,
        'aurea':1987,'bage':1811,'balneario pinhal':1995,'barao':1988,
        'barao de cotegipe':1963,'barao do triunfo':1992,'barra do guarita':1992,'barra do quarai':1995,
        'barra do ribeiro':1959,'barra do rio azul':1992,'barra funda':1992,'barracao':1965,
        'barros cassal':1959,'benjamin constant do sul':1992,'bento goncalves':1890,'boa vista das missoes':1992,
        'boa vista do burica':1965,'boa vista do cadeado':1992,'boa vista do incra':1992,'boa vista do sul':1992,
        'bom jesus':1913,'bom principio':1982,'bom progresso':1992,'bom retiro do sul':1963,
        'boqueirao do leao':1988,'bossoroca':1966,'bozano':1992,'braga':1966,
        'brochier':1988,'butia':1963,'cacapava do sul':1831,'cacequi':1944,
        'cachoeira do sul':1819,'cachoeirinha':1965,'cacique doble':1963,'caibate':1966,
        'caicara':1963,'camaqua':1864,'camargo':1988,'cambara do sul':1963,
        'campestre da serra':1992,'campina das missoes':1963,'campinas do sul':1963,'campo bom':1959,
        'campo novo':1966,'campos borges':1992,'candelaria':1925,'candido godoi':1963,
        'candiota':1992,'canela':1944,'cangucu':1857,'canoas':1939,
        'canudos do vale':1992,'capao bonito do sul':1992,'capao da canoa':1982,'capao do cipo':1992,
        'capao do leao':1982,'capivari do sul':1992,'capela de santana':1992,'capitao':1992,
        'carazinho':1931,'caraa':1992,'carlos barbosa':1959,'carlos gomes':1992,
        'casca':1963,'caseiros':1992,'catuipe':1966,'caxias do sul':1890,
        'centenario':1992,'cerrito':1995,'cerro branco':1992,'cerro grande':1992,
        'cerro grande do sul':1988,'cerro largo':1955,'chapada':1963,'charqueadas':1982,
        'charrua':1992,'chiapetta':1966,'chui':1995,'chuvisca':1995,
        'cidreira':1988,'ciriaco':1963,'colinas':1992,'colorado':1963,
        'condor':1966,'constantina':1963,'coqueiro baixo':1992,'coqueiros do sul':1963,
        'coronel barros':1992,'coronel bicaco':1965,'coronel pilar':1992,'cotipora':1982,
        'coxilha':1992,'crissiumal':1959,'cristal':1992,'cristal do sul':1992,
        'cruz alta':1821,'cruzaltense':1992,'cruzeiro do sul':1963,'david canabarro':1963,
        'derrubadas':1992,'dezesseis de novembro':1988,'dilermando de aguiar':1992,'dois irmaos':1959,
        'dois irmaos das missoes':1992,'dois lajeados':1988,'dom feliciano':1963,'dom pedrito':1872,
        'dom pedro de alcantara':1992,'dona francisca':1965,'doutor mauricio cardoso':1966,'doutor ricardo':1992,
        'eldorado do sul':1988,'encantado':1915,'encruzilhada do sul':1849,'engenho velho':1992,
        'entre-ijuis':1988,'entre rios do sul':1988,'erebango':1987,'erechim':1918,
        'ernestina':1988,'erval grande':1963,'erval seco':1963,'esmeralda':1963,
        'esperanca do sul':1992,'espumoso':1954,'estacao':1987,'estancia velha':1959,
        'esteio':1955,'estrela':1876,'estrela velha':1992,'eugenio de castro':1987,
        'fagundes varela':1992,'farroupilha':1934,'faxinal do soturno':1959,'faxinalzinho':1992,
        'fazenda vilanova':1992,'feliz':1959,'flores da cunha':1924,'floriano peixoto':1987,
        'fontoura xavier':1963,'formigueiro':1963,'forquetinha':1992,'fortaleza dos valos':1992,
        'frederico westphalen':1954,'garibaldi':1870,'garruchos':1966,'gaurama':1959,
        'general camara':1963,'gentil':1988,'getulio vargas':1934,'girua':1955,
        'glorinha':1992,'gramado':1954,'gramado dos loureiros':1992,'gramado xavier':1992,
        'gravatai':1763,'guabiju':1992,'guaiba':1926,'guapore':1903,
        'guarani das missoes':1959,'harmonia':1992,'herval':1881,'herveiras':1992,
        'horizontina':1955,'hulha negra':1992,'humaita':1966,'ibarama':1988,
        'ibiaca':1965,'ibiraiaras':1965,'ibirapuita':1992,'ibiruba':1954,
        'igrejinha':1964,'ijui':1912,'ilopolis':1963,'imbe':1988,
        'imigrante':1988,'independencia':1966,'inhacora':1966,'ipe':1988,
        'ipiranga do sul':1987,'irai':1934,'itaara':1992,'itacurubi':1992,
        'itapuca':1992,'itaqui':1858,'itati':1992,'itatiba do sul':1965,
        'ivora':1988,'ivoti':1964,'jaboticaba':1992,'jacuizinho':1992,
        'jacutinga':1965,'jaguarao':1832,'jaguari':1920,'jaquirana':1988,
        'jari':1992,'joia':1982,'julio de castilhos':1891,'lagoa bonita do sul':1992,
        'lagoa dos tres cantos':1992,'lagoa vermelha':1881,'lagoao':1992,'lajeado':1891,
        'lajeado do bugre':1992,'lavras do sul':1882,'liberato salzano':1965,'lindolfo collor':1992,
        'linha nova':1992,'macambara':1992,'machadinho':1963,'mampituba':1992,
        'manoel viana':1992,'maquine':1992,'marata':1992,'marau':1955,
        'marcelino ramos':1959,'mariana pimentel':1992,'mariano moro':1987,'marques de souza':1992,
        'mata':1965,'mato castelhano':1992,'mato leitao':1992,'mato queimado':1992,
        'maximiliano de almeida':1965,'minas do leao':1992,'miraguai':1966,'montauri':1988,
        'monte alegre dos campos':1992,'monte belo do sul':1992,'montenegro':1873,'mormaco':1992,
        'morrinhos do sul':1992,'morro redondo':1988,'morro reuter':1992,'mostardas':1963,
        'mucum':1914,'muitos capoes':1992,'muliterno':1988,'nao-me-toque':1954,
        'nicolau vergueiro':1992,'nonoai':1963,'nova alvorada':1988,'nova araca':1988,
        'nova bassano':1964,'nova boa vista':1992,'nova brescia':1964,'nova candelaria':1992,
        'nova esperanca do sul':1988,'nova hartz':1992,'nova padua':1992,'nova palma':1965,
        'nova petropolis':1955,'nova prata':1924,'nova ramada':1992,'nova roma do sul':1988,
        'nova santa rita':1992,'novo barreiro':1992,'novo cabrais':1992,'novo hamburgo':1927,
        'novo machado':1992,'novo tiradentes':1992,'novo xingu':1992,'osorio':1857,
        'paim filho':1963,'palmares do sul':1992,'palmeira das missoes':1874,'palmitinho':1963,
        'panambi':1955,'pantano grande':1992,'parai':1988,'paraiso do sul':1988,
        'pareci novo':1992,'parobe':1982,'passa sete':1992,'passo do sobrado':1992,
        'passo fundo':1857,'paulo bento':1992,'paverama':1988,'pedras altas':1992,
        'pedro osorio':1959,'pejucara':1966,'pelotas':1835,'picada cafe':1992,
        'pinhal':1992,'pinhal da serra':1992,'pinhal grande':1992,'pinheirinho do vale':1992,
        'pinheiro machado':1878,'pirapo':1987,'piratini':1830,'planalto':1963,
        'poco das antas':1992,'pontao':1992,'ponte preta':1987,'portao':1963,
        'porto alegre':1772,'porto lucena':1963,'porto maua':1992,'porto vera cruz':1992,
        'porto xavier':1966,'pouso novo':1992,'presidente lucena':1992,'progresso':1988,
        'protasio alves':1988,'putinga':1963,'quarai':1875,'quatro irmaos':1992,
        'quevedos':1992,'quinze de novembro':1966,'redentora':1965,'relvado':1988,
        'restinga seca':1959,'rio dos indios':1992,'rio grande':1751,'rio pardo':1809,
        'riozinho':1988,'roca sales':1959,'rodeio bonito':1963,'rolador':1992,
        'rolante':1954,'ronda alta':1963,'rondinha':1963,'roque gonzales':1966,
        'rosario do sul':1876,'sagrada familia':1992,'saldanha marinho':1988,'salto do jacui':1982,
        'salvador das missoes':1992,'salvador do sul':1963,'sananduva':1965,'santa barbara do sul':1959,
        'santa cecilia do sul':1992,'santa clara do sul':1992,'santa cruz do sul':1878,'santa margarida do sul':1992,
        'santa maria':1858,'santa maria do herval':1988,'santa rosa':1931,'santa tereza':1992,
        'santa vitoria do palmar':1872,'santana da boa vista':1965,'santana do livramento':1857,'santiago':1884,
        'santo angelo':1873,'santo antonio da patrulha':1809,'santo antonio das missoes':1982,'santo antonio do palma':1992,
        'santo antonio do planalto':1992,'santo augusto':1959,'santo cristo':1955,'santo expedito do sul':1992,
        'sao borja':1834,'sao domingos do sul':1988,'sao francisco de assis':1884,'sao francisco de paula':1878,
        'sao gabriel':1846,'sao jeronimo':1938,'sao joao da urtiga':1992,'sao joao do polesine':1992,
        'sao jorge':1988,'sao jose das missoes':1992,'sao jose do herval':1992,'sao jose do hortencio':1992,
        'sao jose do inhacora':1992,'sao jose do norte':1831,'sao jose do ouro':1965,'sao jose do sul':1992,
        'sao jose dos ausentes':1992,'sao leopoldo':1824,'sao lourenco do sul':1884,'sao luiz gonzaga':1830,
        'sao marcos':1963,'sao martinho':1966,'sao martinho da serra':1992,'sao miguel das missoes':1988,
        'sao nicolau':1830,'sao paulo das missoes':1966,'sao pedro da serra':1992,'sao pedro das missoes':1992,
        'sao pedro do butia':1992,'sao pedro do sul':1926,'sao sebastiao do cai':1875,'sao sepe':1876,
        'sao valentim':1965,'sao valentim do sul':1992,'sao valerio do sul':1992,'sao vendelino':1988,
        'sao vicente do sul':1876,'sapiranga':1955,'sapucaia do sul':1961,'sarandi':1964,
        'seberi':1959,'sede nova':1966,'segredo':1988,'selbach':1963,
        'senador salgado filho':1992,'sentinela do sul':1992,'serafina correa':1960,'serio':1992,
        'sertao':1963,'sertao santana':1992,'sete de setembro':1992,'severiano de almeida':1963,
        'silveira martins':1988,'sinimbu':1992,'sobradinho':1963,'soledade':1875,
        'tabai':1992,'tapejara':1955,'tapera':1955,'tapes':1963,
        'taquara':1886,'taquari':1849,'taquarucu do sul':1992,'tavares':1988,
        'tenente portela':1955,'terra de areia':1988,'teutonia':1981,'tio hugo':1992,
        'tiradentes do sul':1992,'toropi':1992,'torres':1878,'tramandai':1965,
        'travesseiro':1992,'tres arroios':1987,'tres cachoeiras':1988,'tres coroas':1959,
        'tres de maio':1959,'tres forquilhas':1988,'tres palmeiras':1987,'tres passos':1944,
        'trindade do sul':1987,'triunfo':1831,'tucunduva':1959,'tunas':1988,
        'tupanci do sul':1992,'tupancireta':1928,'tupandi':1992,'tuparendi':1963,
        'turucu':1992,'ubiretama':1992,'uniao da serra':1992,'unistalda':1992,
        'uruguaiana':1846,'vacaria':1850,'vale do sol':1992,'vale real':1992,
        'vale verde':1992,'vanini':1988,'venancio aires':1891,'vera cruz':1959,
        'veranopolis':1898,'vespasiano correa':1992,'viadutos':1959,'viamao':1741,
        'vicente dutra':1965,'victor graeff':1992,'vila flores':1988,'vila langaro':1992,
        'vila maria':1988,'vila nova do sul':1992,'vista alegre':1992,'vista alegre do prata':1992,
        'vista gaucha':1992,'vitoria das missoes':1992,'westfalia':1992,'xangri-la':1992,
    },
}

# ─── Utilitários ──────────────────────────────────────────────────────────────

def _norm(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().strip()

def nome_arquivo(nome):
    return _norm(nome).replace('-', ' ').replace(' ', '_')

def _fonte(path, size):
    return ImageFont.truetype(str(path), size)

def _quebrar_nome(nome, limite=20):
    """Quebra em 2 linhas se >limite chars, no melhor espaço perto do meio."""
    if len(nome) <= limite:
        return nome
    palavras = nome.split()
    melhor, melhor_diff = nome, len(nome)
    for i in range(1, len(palavras)):
        l1 = ' '.join(palavras[:i])
        l2 = ' '.join(palavras[i:])
        diff = abs(len(l1) - len(l2))
        if diff < melhor_diff:
            melhor_diff, melhor = diff, l1 + '\n' + l2
    return melhor

def _fonte_cidade(nome, max_w=3300, max_h=None):
    """Fraunces Black, tamanho máximo que cabe em max_w (e max_h se informado)."""
    d   = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    txt = _quebrar_nome(nome).upper()
    for size in range(370, 130, -10):
        f = _fonte(FONT_FRAUNCES, size)
        w = max(d.textbbox((0, 0), ln, font=f)[2] for ln in txt.split('\n'))
        if w > max_w:
            continue
        if max_h is not None:
            bb = d.multiline_textbbox((0, 0), txt, font=f)
            if bb[3] - bb[1] > max_h:
                continue
        return f
    return _fonte(FONT_FRAUNCES, 140)


# ─── Ano de fundação ──────────────────────────────────────────────────────────

_WIKI_HEADERS = {'User-Agent': 'ArteLojas/1.0 (city-art-generator)'}

def buscar_ano_fundacao(nome_cidade, uf):
    """Retorna o ano de fundação: dicionário local primeiro, depois Wikipedia."""
    local = _ANOS_FUNDACAO.get(uf, {}).get(_norm(nome_cidade))
    if local:
        return local
    try:
        uf_nome = UF_NOMES.get(uf, uf)
        r = requests.get(
            "https://pt.wikipedia.org/w/api.php",
            params={
                'action': 'query', 'list': 'search',
                'srsearch': f'{nome_cidade} {uf_nome} município',
                'format': 'json', 'srlimit': 5,
            },
            headers=_WIKI_HEADERS,
            timeout=10,
        )
        results = r.json().get('query', {}).get('search', [])
        if not results:
            return None
        # 1º: cidade + estado no título (ex: "Araucária (Paraná)")
        # 2º: só a cidade no título
        # 3º: primeiro resultado
        nome_n = _norm(nome_cidade)
        uf_n   = _norm(uf_nome)
        title = (
            next((x['title'] for x in results
                  if nome_n in _norm(x['title']) and uf_n in _norm(x['title'])), None)
            or next((x['title'] for x in results
                     if nome_n in _norm(x['title'])), None)
            or results[0]['title']
        )

        # 1ª tentativa: wikitext bruto — captura campos do infobox
        r_wt = requests.get(
            "https://pt.wikipedia.org/w/api.php",
            params={
                'action': 'query', 'prop': 'revisions',
                'rvprop': 'content', 'rvslots': 'main',
                'titles': title, 'format': 'json', 'redirects': '1',
            },
            headers=_WIKI_HEADERS,
            timeout=10,
        )
        pages = r_wt.json().get('query', {}).get('pages', {})
        for page in pages.values():
            wikitext = (page.get('revisions') or [{}])[0].get('slots', {}).get('main', {}).get('*', '')
            # Campos de infobox: |data_fundação = ..., |fundação = ..., |data_criação = ...
            infobox_pats = [
                r'\|\s*data_funda[çc][aã]o\s*=\s*[^}\n]*?(\b1[89]\d{2}\b)',
                r'\|\s*funda[çc][aã]o\s*=\s*[^}\n]*?(\b1[89]\d{2}\b)',
                r'\|\s*data_cria[çc][aã]o\s*=\s*[^}\n]*?(\b1[89]\d{2}\b)',
                r'\|\s*emancipa[çc][aã]o\s*=\s*[^}\n]*?(\b1[89]\d{2}\b)',
                r'\|\s*data\s*=\s*[^}\n]*?(\b1[89]\d{2}\b)',
            ]
            for pat in infobox_pats:
                m = re.search(pat, wikitext, re.IGNORECASE)
                if m:
                    return int(m.group(1))

            # 2ª tentativa: texto corrido do artigo
            text = wikitext[:8000]
            body_pats = [
                r'(?:fundad[ao]|criad[ao]|instalad[ao]|emancipad[ao])\s+'
                r'(?:de\s+\w+\s+de\s+)?(?:em\s+)?(?:\d{1,2}[ºo°]?\s+de\s+\w+\s+de\s+)?(\d{4})',
                r'\bEm\s+(\d{4})\s+foi\s+(?:fundad[ao]|criad[ao]|instalad[ao]|emancipad[ao])',
                r'(?:fundad[ao]|criad[ao]|instalad[ao]|emancipad[ao]).*?(\b1[89]\d{2}\b)',
            ]
            for pat in body_pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return None


# ─── SVG helpers ──────────────────────────────────────────────────────────────

def _svg_solido_bytes(uf):
    svg_str = (PASTA_SVG / f"{uf}_branco.svg").read_text(encoding='utf-8')
    svg_str = re.sub(r'fill:[^;}"\']+',        'fill:#ffffff',   svg_str)
    svg_str = re.sub(r'fill-opacity:[^;}"\']+', 'fill-opacity:1', svg_str)
    svg_str = re.sub(r'stroke:[^;}"\']+',       'stroke:none',    svg_str)
    return svg_str.encode('utf-8')


def _pintar_municipio(tree, uf, nome_cidade, mun_fill='#d6ba8d'):
    from engine.utils.svg_pendentes import (
        preprocessar_svg, calcular_bounds_municipio_em_svg,
        calcular_bounds_coords, extrair_todas_coordenadas,
        encontrar_melhor_path, baixar_bounds_estado,
    )
    muns   = requests.get(
        f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
        timeout=20).json()
    codigo = next((m["id"] for m in muns if _norm(m["nome"]) == _norm(nome_cidade)), None)
    if not codigo:
        raise ValueError(f"Município não encontrado: {nome_cidade}/{uf}")

    gj         = requests.get(
        f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}"
        "?formato=application/vnd.geo+json&qualidade=minima", timeout=20).json()
    bounds_mun = calcular_bounds_coords(extrair_todas_coordenadas(gj))
    bounds_est = baixar_bounds_estado(uf)
    bounds_svg, paths_info = preprocessar_svg(PASTA_SVG / f"{uf}_branco.svg")

    if not (bounds_mun and bounds_est and bounds_svg and paths_info):
        raise ValueError("Bounds incompletos")

    bounds_mun_svg = calcular_bounds_municipio_em_svg(bounds_mun, bounds_est, bounds_svg)
    melhor = encontrar_melhor_path(paths_info, bounds_mun_svg, nome_cidade)
    if not melhor:
        raise ValueError("Path do município não encontrado")

    path_el = None
    if melhor.get('elem_id'):
        for e in tree.iter():
            if e.get('id') == melhor['elem_id']:
                path_el = e; break
    if path_el is None and melhor.get('d_prefix'):
        for e in tree.iter():
            if e.get('d', '').startswith(melhor['d_prefix']):
                path_el = e; break
    if path_el is None:
        raise ValueError("Elemento SVG não re-localizado")

    style = path_el.get('style', '')
    style = re.sub(r'fill:[^;]+',         f'fill:{mun_fill}',  style)
    style = re.sub(r'fill-opacity:[^;]+', 'fill-opacity:1',     style)
    if 'fill:'         not in style: style += f';fill:{mun_fill}'
    if 'fill-opacity:' not in style: style += ';fill-opacity:1'
    path_el.set('style', style)


def _svg_municipio_isolado(uf, nome_cidade, mun_fill='#d6ba8d'):
    svg_str = (PASTA_SVG / f"{uf}_branco.svg").read_text(encoding='utf-8')
    svg_str = svg_str.replace('fill:#000000', 'fill:#ffffff')  # evita artefatos escuros no SC
    svg_str = re.sub(r'fill:[^;}"\']+',        'fill:none',      svg_str)
    svg_str = re.sub(r'fill-opacity:[^;}"\']+', 'fill-opacity:0', svg_str)
    svg_str = re.sub(r'stroke:[^;}"\']+',       'stroke:none',    svg_str)
    parser = etree.XMLParser(remove_blank_text=True)
    tree   = etree.fromstring(svg_str.encode('utf-8'), parser)
    _pintar_municipio(tree, uf, nome_cidade, mun_fill=mun_fill)
    return etree.tostring(tree, encoding='unicode').encode('utf-8')


# ─── Renderização ─────────────────────────────────────────────────────────────

def _svg_para_img(svg_bytes, vis_w, crop_box=None, dpi=300):
    png = cairosvg.svg2png(bytestring=svg_bytes, dpi=dpi)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    if crop_box is None:
        arr = np.array(img)
        vis = arr[:, :, 3] > 10
        ys, xs = np.where(vis)
        if len(xs) == 0:
            return img, (0, 0, img.width - 1, img.height - 1)
        pad = 20
        crop_box = (
            max(0,             int(xs.min()) - pad),
            max(0,             int(ys.min()) - pad),
            min(img.width - 1, int(xs.max()) + pad),
            min(img.height - 1,int(ys.max()) + pad),
        )
    x0, y0, x1, y1 = crop_box
    cropped = img.crop((x0, y0, x1 + 1, y1 + 1))
    scale   = vis_w / (x1 - x0 + 1)
    return cropped.resize((vis_w, int(round((y1 - y0 + 1) * scale))), Image.LANCZOS), crop_box


def _criar_outline_estado(img_solid, ring_px=OUTLINE_PX, cor=(255, 255, 255, 255)):
    from PIL import ImageFilter
    arr       = np.array(img_solid)
    solid     = arr[:, :, 3] > 10
    solid_pil = Image.fromarray((solid * 255).astype(np.uint8), 'L')
    # Closing morfológico: fecha costuras entre municípios (artefatos de anti-aliasing)
    solid_pil = solid_pil.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    solid     = np.array(solid_pil) > 0
    rs        = ring_px * 2 + 1
    outer     = np.array(solid_pil.filter(ImageFilter.MaxFilter(rs))) > 0
    ring      = outer & ~solid
    out       = np.zeros((img_solid.height, img_solid.width, 4), dtype=np.uint8)
    out[ring] = list(cor)
    return Image.fromarray(out, 'RGBA')


# ─── Composição final ─────────────────────────────────────────────────────────

def gerar_arte_v2c(
    nome_cidade,
    uf,
    pasta_destino,
    nome_base,
    versao="escura",
    nome_exibicao=None,
    png_dpi=300,
):
    pasta_destino.mkdir(parents=True, exist_ok=True)
    pal = _PALETAS[versao]
    cfg = UF_CONFIG.get(uf, _DEFAULT_CFG)
    vis_w = cfg["vis_w"]
    nome_topo = nome_exibicao or nome_cidade

    print(f"  🗺️  SVG V2-C ({uf}/{nome_cidade}) [{versao}]...")

    img_solid, crop_box = _svg_para_img(_svg_solido_bytes(uf), vis_w, dpi=png_dpi)
    img_outline = _criar_outline_estado(img_solid, cor=pal['outline'])
    img_mun, _  = _svg_para_img(_svg_municipio_isolado(uf, nome_cidade, mun_fill=pal['mun_fill']), vis_w, crop_box=crop_box, dpi=png_dpi)

    # ── Busca ano de fundação ──────────────────────────────────────────────────
    print(f"  📅 Buscando ano de fundação...")
    ano = buscar_ano_fundacao(nome_cidade, uf)
    if ano:
        print(f"     → {ano}")
    else:
        print(f"     → não encontrado")

    # ── Medir alturas do rodapé ANTES de definir fonte da cidade ──────────────
    ANO_SIZE    = 120
    ESTADO_SIZE = 260
    font_ano    = _fonte(FONT_FRAUNCES_ITALIC, ANO_SIZE)
    font_estado = _fonte(FONT_FRAUNCES, ESTADO_SIZE)
    d_m         = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb_ano      = d_m.textbbox((0, 0), "est. 0000",                   font=font_ano)
    bb_est      = d_m.textbbox((0, 0), UF_NOMES.get(uf, uf).upper(),  font=font_estado)
    ano_h       = bb_ano[3] - bb_ano[1]
    estado_h    = bb_est[3] - bb_est[1]

    # ── Altura máxima para a cidade (tudo tem que caber no canvas) ────────────
    CITY_TOP      = 200
    BOTTOM_MARGIN = 160
    GAP_DIV_MAP   = 90
    GAP_MAP_ANO   = 110
    GAP_ANO_EST   = 55

    avail_city_h = (CANVAS_H
                    - CITY_TOP - 80 - GAP_DIV_MAP
                    - img_solid.height
                    - GAP_MAP_ANO - ano_h
                    - GAP_ANO_EST - estado_h
                    - BOTTOM_MARGIN)

    # Fonte da cidade limitada por largura E altura disponível
    txt_cidade = _quebrar_nome(nome_topo).upper()
    font_city = _fonte_cidade(nome_topo, max_w=3300, max_h=max(200, avail_city_h))
    d_tmp       = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb_city     = d_tmp.multiline_textbbox((0, 0), txt_cidade, font=font_city)
    city_h      = bb_city[3] - bb_city[1]

    # ── Layout top-down ───────────────────────────────────────────────────────
    city_center = CITY_TOP + city_h // 2
    city_bottom = CITY_TOP + city_h
    divider_y   = city_bottom + 80
    map_top     = divider_y + GAP_DIV_MAP
    map_vis_x   = (CANVAS_W - vis_w) // 2
    map_bottom  = map_top + img_solid.height
    ano_y       = map_bottom + GAP_MAP_ANO + ano_h // 2
    estado_y    = ano_y + ano_h // 2 + GAP_ANO_EST + estado_h // 2

    # ── Canvas ────────────────────────────────────────────────────────────────
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG)

    # Mapa
    canvas.paste(img_outline, (map_vis_x, map_top), img_outline)
    canvas.paste(img_mun,     (map_vis_x, map_top), img_mun)

    # ── Tipografia ─────────────────────────────────────────────────────────────
    draw = ImageDraw.Draw(canvas)

    # Cidade grande no topo
    draw.multiline_text(
        (CANVAS_W // 2, city_center), txt_cidade,
        font=font_city, fill=pal['text'], anchor='mm', align='center',
    )

    # Linha divisória (gold)
    draw.line(
        [(CANVAS_W // 2 - 700, divider_y), (CANVAS_W // 2 + 700, divider_y)],
        fill=pal['rule'], width=3,
    )

    # Ano de fundação (placeholder quando não encontrado)
    txt_ano = f"est. {ano}" if ano else "est. ——"
    draw.text(
        (CANVAS_W // 2, ano_y), txt_ano,
        font=font_ano,
        fill=pal['accent'], anchor='mm',
    )

    # Nome completo do estado
    nome_estado = UF_NOMES.get(uf, uf)
    draw.text(
        (CANVAS_W // 2, estado_y), nome_estado.upper(),
        font=font_estado,
        fill=pal['text'], anchor='mm',
    )

    sufixo = 'preto' if versao == 'escura' else 'branco'
    saida  = pasta_destino / f"{nome_base}_arte_{sufixo}.png"
    canvas.save(str(saida), "PNG")
    print(f"  ✅ {saida}")
    return str(saida)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gerar arte estilo V2-C")
    parser.add_argument("--cidade", help="'Cidade,UF'")
    parser.add_argument("--uf", nargs='+', metavar='UF')
    parser.add_argument("--clara", action="store_true")
    args    = parser.parse_args()
    versoes = ['clara'] if args.clara else ['escura', 'clara']

    from coordenadas import buscar_codigo_ibge
    import time

    LOG_FALHAS = PASTA_BASE / "premium_falhas.txt"
    falhas = []

    def _processar(cidade, uf):
        _, nome_of = buscar_codigo_ibge(uf, cidade)
        if not nome_of: nome_of = cidade
        n_arq    = nome_arquivo(nome_of)
        pasta_uf = PASTA_SAIDA / uf
        print(f"\n🎨 {nome_of}/{uf}")
        for v in versoes:
            ultimo_erro = None
            for tentativa in range(3):
                try:
                    gerar_arte_v2c(nome_of, uf, pasta_uf, n_arq, versao=v)
                    ultimo_erro = None
                    break
                except Exception as e:
                    ultimo_erro = e
                    if tentativa < 2:
                        print(f"  ⚠️  Tentativa {tentativa+1} falhou ({e}) — retry...")
                        time.sleep(2)
                    else:
                        import traceback
                        print(f"  ❌ Falhou após 3 tentativas: {e}")
                        traceback.print_exc()
                        falhas.append(f"{nome_of},{uf},{v},{e}")

    if args.cidade:
        if ',' not in args.cidade:
            print("❌ Use 'Cidade,UF'"); sys.exit(1)
        cidade, uf = args.cidade.rsplit(',', 1)
        _processar(cidade.strip(), uf.strip().upper())
        return

    filtro_ufs = {u.upper() for u in args.uf} if args.uf else None
    cidades = []
    with open(ARQUIVO_CSV, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            cidade = row['cidade'].strip()
            uf     = row['uf'].strip().strip('"').upper()
            if filtro_ufs and uf not in filtro_ufs: continue
            cidades.append((cidade, uf))

    print(f"\n{'='*60}\n   GERAR ARTE V2-C — {len(cidades)} cidade(s)\n{'='*60}")
    for i, (cidade, uf) in enumerate(cidades):
        print(f"\n[{i+1}/{len(cidades)}]", end=" ")
        _processar(cidade, uf)

    print(f"\n{'='*60}")
    if falhas:
        with open(LOG_FALHAS, 'w', encoding='utf-8') as f:
            f.write("cidade,uf,versao,erro\n")
            for linha in falhas:
                f.write(linha + "\n")
        print(f"❌ {len(falhas)} falha(s) — veja {LOG_FALHAS}")
    else:
        print("✅ Todas as cidades geradas sem falhas.")


# --- Map Engine API -----------------------------------------------------------


def gerar(localidades: list[dict], opcoes: dict | None = None) -> Image.Image:
    opcoes = opcoes or {}
    if not localidades:
        raise ValueError("localidades vazia")
    loc = localidades[0]
    uf = loc["uf"].upper()
    nome_ibge = loc["municipio"]
    topo = opcoes.get("texto_linha2") or nome_ibge
    versao = "escura" if opcoes.get("cor", "preto") == "preto" else "clara"
    dpi_svg = (
        int(os.environ.get("PREVIEW_SVG_DPI", "96"))
        if opcoes.get("resolucao") == "preview"
        else int(os.environ.get("FINAL_DPI", "300"))
    )
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        gerar_arte_v2c(
            nome_ibge, uf, td, "mapout", versao=versao, nome_exibicao=topo, png_dpi=dpi_svg
        )
        suf = "preto" if versao == "escura" else "branco"
        p = td / f"mapout_arte_{suf}.png"
        img = Image.open(p).convert("RGBA")
    if opcoes.get("resolucao") == "preview":
        max_dim = int(os.environ.get("PREVIEW_MAX_DIM", "800"))
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img


if __name__ == "__main__":
    main()
