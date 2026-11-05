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

# Nome do dia como a PRF escreve (em minúsculas na silver), na ordem do
# dayofweek do Spark: 1 = domingo ... 7 = sábado.
DIAS_SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira",
               "quinta-feira", "sexta-feira", "sábado"]

# Nível de confiança dos intervalos de Wilson nos agregados (95%).
Z_95 = 1.959963984540054


def wilson(graves: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Intervalo de Wilson para a proporção graves/n (referência para o teste do Spark)."""
    p = graves / n
    denom = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denom
    meia = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centro - meia), min(1.0, centro + meia)

# Em janeiro de 2021 a PRF trocou a lista de causas: as ~30 causas amplas de
# 2019-2020 ("Falta de Atenção à Condução") deram lugar a ~70 mais finas
# ("Reação tardia...", "Ausência de reação..."), sem correspondência 1 para 1
# (resultados/fase3_categorias_por_ano.csv e fase3_transicao_por_mes.csv).
# A causa só é comparada de 2021 em diante.
INICIO_LISTA_CAUSAS = 2021

# Renomeações dentro da lista nova de causas (mesmo conceito, outro nome).
CAUSA_PADRONIZADA = {
    "Transitar no Acostamento": "Transitar no acostamento",
    "Ingestão de álcool e/ou substâncias psicoativas pelo pedestre":
        "Ingestão de álcool ou de substâncias psicoativas pelo pedestre",
    "Pedestre - Ingestão de álcool/ substâncias psicoativas":
        "Ingestão de álcool ou de substâncias psicoativas pelo pedestre",
}

# O tipo de acidente mudou entre janeiro e fevereiro de 2021: "Colisão lateral"
# foi dividida por sentido e os dois tipos de colisão com objeto foram unidos.
# Juntar as categorias finas na ampla é seguro nos dois sentidos do tempo.
TIPO_PADRONIZADO = {
    "Colisão lateral mesmo sentido": "Colisão lateral",
    "Colisão lateral sentido oposto": "Colisão lateral",
    "Colisão com objeto estático": "Colisão com objeto",
    "Colisão com objeto em movimento": "Colisão com objeto",
}
