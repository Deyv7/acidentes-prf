"""Regras e constantes do projeto, em Python puro (sem Spark).

Ficam aqui para que a validação da fonte (src/validar_fonte.py), a silver e os
testes usem exatamente os mesmos valores.
"""
from datetime import date

# As 30 colunas do arquivo agrupado por ocorrência, na ordem da fonte.
# Iguais de 2017 a 2026 (resultados/fase0_layout_por_ano.csv).
COLUNAS_FONTE = [
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km", "municipio",
    "causa_acidente", "tipo_acidente", "classificacao_acidente", "fase_dia",
    "sentido_via", "condicao_metereologica", "tipo_pista", "tracado_via",
    "uso_solo", "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
    "ignorados", "feridos", "veiculos", "latitude", "longitude", "regional",
    "delegacia", "uop",
]

CONTAGENS = ["pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
             "ignorados", "feridos", "veiculos"]

# Primeiro ano do sistema BAT. Antes disso o registro era outro (BR-Brasil).
ANO_INICIAL = 2017
# Último ano completo. 2026 ainda está em andamento e fica fora da bronze.
ANO_FINAL = 2025

# Em abril de 2018 a proporção de "Sem Vítimas" cai de ~30% para ~18% e não
# volta (resultados/fase0_sem_vitimas_por_mes.csv). Antes dessa data, total de
# acidentes e % de graves não são comparáveis com o período seguinte.
INICIO_SERIE_ESTAVEL = date(2018, 4, 1)

# Recorte da análise e da gold: anos completos depois da quebra.
ANOS_ANALISE = list(range(2019, 2026))

CLASSIF_FATAL = "Com Vítimas Fatais"
CLASSIF_FERIDAS = "Com Vítimas Feridas"
CLASSIF_SEM = "Sem Vítimas"

# Extremos do território continental com folga de ~0,01 grau, mais uma caixa
# só para Fernando de Noronha (PE), que tem a BR-363. Alargar a caixa
# continental até Noronha deixaria passar coordenadas erradas no mar
# (docs/validacao-fonte.md, seção "Latitude e longitude").
LAT_MIN, LAT_MAX = -33.76, 5.28
LON_MIN, LON_MAX = -74.00, -34.78
NORONHA = (-3.95, -3.80, -32.55, -32.35)  # lat_min, lat_max, lon_min, lon_max


def dentro_do_brasil(lat: float, lon: float) -> bool:
    if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
        return True
    return NORONHA[0] <= lat <= NORONHA[1] and NORONHA[2] <= lon <= NORONHA[3]
