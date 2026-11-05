"""Exporta resultados/ para os JSON da página em web/public/dados/.

Todo número que a página mostra sai daqui, lido dos arquivos que o pipeline
gravou em resultados/. A página não tem número escrito à mão.

Só biblioteca padrão; roda fora do container:
    python -I src/exportar_web.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ / "resultados"
DESTINO = RAIZ / "web" / "public" / "dados"
MALHA_UF = RAIZ / "dados_externos" / "malha_uf_ibge.geojson"

RECORTES = ["ano", "uf", "br", "trecho_10km", "municipio", "hora", "dia_semana", "mes",
            "fase_dia", "condicao_meteorologica", "tipo_pista", "tipo_acidente", "causa_acidente"]

# Comparação com a média, em uma letra para o JSON ficar menor.
COMPARACAO = {"acima": "a", "abaixo": "b", "indistinguível": "i",
              "amostra pequena": "p", "fora da comparação": "f"}

# Código IBGE da UF -> sigla (para o contorno do mapa).
UF_IBGE = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
           "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
           "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
           "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"}


def ler(nome: str) -> list[dict]:
    with open(RESULTADOS / nome, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def r4(x: str) -> float | None:
    return None if x in ("", None) else round(float(x), 4)


def inteiro(x: str) -> int | None:
    return None if x in ("", None) else int(x)


def recorte(nome: str) -> dict:
    """Formato colunar: uma lista por campo, na ordem do CSV (posição, depois tamanho)."""
    linhas = ler(f"fase3_recorte_{nome}.csv")
    return {
        "media": float(linhas[0]["media_recorte"]),
        "media_com_vitima": float(linhas[0]["media_recorte_com_vitima"]),
        "valor": [r["valor"] for r in linhas],
        "n": [int(r["ocorrencias"]) for r in linhas],
        "graves": [int(r["graves"]) for r in linhas],
        "pct": [r4(r["pct_graves"]) for r in linhas],
        "inf": [r4(r["ic95_inf"]) for r in linhas],
        "sup": [r4(r["ic95_sup"]) for r in linhas],
        "comp": [COMPARACAO[r["comparacao"]] for r in linhas],
        "pos": [inteiro(r["posicao"]) for r in linhas],
        "n_vitima": [int(r["com_vitima"]) for r in linhas],
        "pct_vitima": [r4(r["pct_graves_com_vitima"]) for r in linhas],
        "inf_vitima": [r4(r["ic95_inf_com_vitima"]) for r in linhas],
        "sup_vitima": [r4(r["ic95_sup_com_vitima"]) for r in linhas],
        "comp_vitima": [COMPARACAO[r["comparacao_com_vitima"]] for r in linhas],
        "com_morto": [int(r["com_morto"]) for r in linhas],
        "mortos": [int(r["mortos"]) for r in linhas],
    }


def resumo(recortes: dict) -> dict:
    ano = recortes["ano"]
    total, graves = sum(ano["n"]), sum(ano["graves"])
    for nome, r in recortes.items():  # cada recorte soma o total da gold
        assert (sum(r["n"]), sum(r["graves"])) == (total, graves), nome
    gold = {r["recorte"]: r for r in ler("fase2_recortes_gold.csv")}
    assert (int(gold["ano"]["ocorrencias"]), int(gold["ano"]["graves"])) == (total, graves)

    qual: dict[str, dict] = {}
    for r in ler("fase2_qualidade.csv"):
        q = qual.setdefault(r["regra"], {"bloqueante": r["bloqueante"] == "True",
                                         "tratamento": r["tratamento"], "por_ano": {}})
        q["por_ano"][r["ano"]] = int(r["linhas_reprovadas"])
    resumo_rec = {r["recorte"]: {k: (float(v) if k.startswith("media") else int(v))
                                 for k, v in r.items() if k != "recorte"}
                  for r in ler("fase3_resumo_recortes.csv")}
    return {
        "anos": [min(int(v) for v in ano["valor"]), max(int(v) for v in ano["valor"])],
        "ocorrencias": total,
        "graves": graves,
        "mortos": sum(ano["mortos"]),
        "media": graves / total,
        "media_com_vitima": ano["media_com_vitima"],
        "n_min": 100,
        "qualidade": qual,
        "resumo_recortes": resumo_rec,
    }


def transicao() -> dict:
    saida: dict[str, dict] = {}
    for r in ler("fase3_transicao_por_mes.csv"):
        s = saida.setdefault(r["coluna"], {"mes": [], "ocorrencias": [], "lista_antiga": []})
        s["mes"].append(f"{r['ano']}-{int(r['mes']):02d}")
        s["ocorrencias"].append(int(r["ocorrencias"]))
        s["lista_antiga"].append(int(r["valor_so_da_lista_antiga"]))
    return saida


def mapa() -> dict:
    linhas = ler("fase3_grade_mapa.csv")
    passo = min(abs(float(a["lat_celula"]) - float(b["lat_celula"]))
                for a, b in zip(linhas, linhas[1:]) if a["lat_celula"] != b["lat_celula"])
    g = json.loads(MALHA_UF.read_text(encoding="utf-8"))
    contorno = []
    for f in g["features"]:
        geo = f["geometry"]
        poligonos = [geo["coordinates"]] if geo["type"] == "Polygon" else geo["coordinates"]
        for p in poligonos:
            contorno.append({"uf": UF_IBGE[f["properties"]["codarea"]],
                             "anel": [[round(x, 3), round(y, 3)] for x, y in p[0]]})
    return {
        "passo": passo,
        "media": float(linhas[0]["media"]),
        "lat": [float(r["lat_celula"]) for r in linhas],
        "lon": [float(r["lon_celula"]) for r in linhas],
        "n": [int(r["ocorrencias"]) for r in linhas],
        "graves": [int(r["graves"]) for r in linhas],
        "pct": [r4(r["pct_graves"]) for r in linhas],
        "inf": [r4(r["ic95_inf"]) for r in linhas],
        "sup": [r4(r["ic95_sup"]) for r in linhas],
        "comp": [COMPARACAO[r["comparacao"]] for r in linhas],
        "contorno": contorno,
    }


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    recortes = {nome: recorte(nome) for nome in RECORTES}
    arquivos = {
        "resumo.json": resumo(recortes),
        "recortes.json": recortes,
        "transicao.json": transicao(),
        "mapa.json": mapa(),
    }
    for nome, dados in arquivos.items():
        texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
        (DESTINO / nome).write_text(texto, encoding="utf-8")
        print(f"{nome}: {len(texto.encode('utf-8')) // 1024} KB")


if __name__ == "__main__":
    main()
