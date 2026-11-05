"""Compara a saída dos notebooks 02_silver e 03_gold no Databricks com a execução local.

Lê o JSON de `databricks jobs get-run-output` das tarefas silver e gold e os
CSVs gerados por src/executar_local.py, e grava:
- resultados/fase1_conferencia_databricks.csv (silver, por ano);
- resultados/fase2_conferencia_databricks.csv (qualidade por ano e regra,
  gold por ano e por recorte);
- resultados/fase3_conferencia_databricks.csv (resumo da análise por recorte).
Sai com erro se algo não bater.

Uso: python -I src/conferir_databricks.py <saida_silver.json> <saida_gold.json> \
         <saida_analise.json> <pasta_resultados>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

MEDIDAS = ["ocorrencias", "graves", "com_morto", "coord_invalida",
           "id_corrigido", "classificacao_imputada"]
# nome da coluna em fase1_conferencia_silver.csv para cada medida
LOCAL = {"ocorrencias": "ocorrencias_silver", "graves": "graves_silver",
         "com_morto": "com_morto_silver"}


def ler_saida(caminho: Path) -> dict:
    saida = json.loads(caminho.read_text(encoding="utf-8"))
    return json.loads(saida["notebook_output"]["result"])


def ler_csv(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gravar(caminho: Path, linhas: list[dict]) -> None:
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def conferir_silver(remoto: dict, resultados: Path) -> bool:
    local = {int(r["ano"]): r for r in ler_csv(resultados / "fase1_conferencia_silver.csv")}
    linhas = []
    for r in remoto["por_ano"]:
        loc = local.get(r["ano"])
        bate = loc is not None and all(r[m] == int(loc[LOCAL.get(m, m)]) for m in MEDIDAS)
        linhas.append({"ano": r["ano"], **{m: r[m] for m in MEDIDAS}, "bate_com_local": bate})
    total_remoto = sum(r["ocorrencias"] for r in linhas)
    ok = (set(local) == {r["ano"] for r in linhas}
          and all(r["bate_com_local"] for r in linhas)
          and remoto["linhas_bronze_vigente"] == total_remoto)
    gravar(resultados / "fase1_conferencia_databricks.csv", linhas)
    print(f"silver: bronze vigente {remoto['linhas_bronze_vigente']}, silver {total_remoto}, "
          f"bate com local: {ok}")
    return ok


def conferir_gold(remoto: dict, resultados: Path) -> bool:
    linhas = []
    qual_local = {(int(r["ano"]), r["regra"]): int(r["linhas_reprovadas"])
                  for r in ler_csv(resultados / "fase2_qualidade.csv")}
    for q in remoto["qualidade"]:
        loc = qual_local.get((q["ano"], q["regra"]))
        linhas.append({"tabela": "qualidade", "chave": f"{q['ano']} {q['regra']}",
                       "databricks": q["linhas_reprovadas"], "local": loc,
                       "bate": loc == q["linhas_reprovadas"]})
    gold_local = {int(r["ano"]): r for r in ler_csv(resultados / "fase2_conferencia_gold.csv")}
    for r in remoto["por_ano"]:
        loc = gold_local.get(r["ano"], {})
        for medida, col in (("ocorrencias", "ocorrencias_gold"), ("graves", "graves_gold")):
            v = int(loc[col]) if col in loc else None
            linhas.append({"tabela": "gold_ocorrencias_modelo", "chave": f"{r['ano']} {medida}",
                           "databricks": r[medida], "local": v, "bate": v == r[medida]})
    rec_local = {r["recorte"]: r for r in ler_csv(resultados / "fase2_recortes_gold.csv")}
    for r in remoto["por_recorte"]:
        loc = rec_local.get(r["recorte"], {})
        for medida in ("valores", "ocorrencias", "graves"):
            v = int(loc[medida]) if medida in loc else None
            linhas.append({"tabela": "gold_graves_por_recorte", "chave": f"{r['recorte']} {medida}",
                           "databricks": r[medida], "local": v, "bate": v == r[medida]})
    ok = (len(remoto["qualidade"]) == len(qual_local)
          and {r["ano"] for r in remoto["por_ano"]} == set(gold_local)
          and {r["recorte"] for r in remoto["por_recorte"]} == set(rec_local)
          and all(l["bate"] for l in linhas))
    gravar(resultados / "fase2_conferencia_databricks.csv", linhas)
    print(f"gold: {len(linhas)} números comparados, {sum(not l['bate'] for l in linhas)} divergentes; "
          f"bate com local: {ok}")
    return ok


def conferir_analise(remoto: dict, resultados: Path) -> bool:
    local = {r["recorte"]: r for r in ler_csv(resultados / "fase3_resumo_recortes.csv")}
    linhas = []
    for r in remoto["resumo"]:
        loc = local.get(r["recorte"], {})
        for medida, v in r.items():
            if medida == "recorte":
                continue
            lv = loc.get(medida)
            if medida.startswith("media"):  # proporção: compara com tolerância
                bate = lv is not None and abs(float(lv) - v) < 1e-9
            else:
                bate = lv is not None and int(lv) == v
            linhas.append({"recorte": r["recorte"], "medida": medida, "databricks": v,
                           "local": lv, "bate": bate})
    ok = {r["recorte"] for r in remoto["resumo"]} == set(local) and all(l["bate"] for l in linhas)
    gravar(resultados / "fase3_conferencia_databricks.csv", linhas)
    print(f"análise: {len(linhas)} números comparados, {sum(not l['bate'] for l in linhas)} divergentes; "
          f"bate com local: {ok}")
    return ok


def main(silver_json: Path, gold_json: Path, analise_json: Path, resultados: Path) -> int:
    ok_silver = conferir_silver(ler_saida(silver_json), resultados)
    ok_gold = conferir_gold(ler_saida(gold_json), resultados)
    ok_analise = conferir_analise(ler_saida(analise_json), resultados)
    return 0 if ok_silver and ok_gold and ok_analise else 1


if __name__ == "__main__":
    sys.exit(main(*(Path(a) for a in sys.argv[1:5])))
