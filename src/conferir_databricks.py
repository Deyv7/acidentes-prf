"""Compara a saída do notebook 02_silver no Databricks com a execução local.

Lê o JSON de `databricks jobs get-run-output` da tarefa silver e
resultados/fase1_conferencia_silver.csv (gerado por src/executar_local.py) e
grava resultados/fase1_conferencia_databricks.csv. Sai com erro se algo não bater.

Uso: python -I src/conferir_databricks.py <saida_da_tarefa.json> <pasta_resultados>
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


def main(saida_json: Path, resultados: Path) -> int:
    saida = json.loads(saida_json.read_text(encoding="utf-8"))
    remoto = json.loads(saida["notebook_output"]["result"])
    local = {int(r["ano"]): r for r in
             csv.DictReader(open(resultados / "fase1_conferencia_silver.csv", encoding="utf-8"))}

    linhas = []
    for r in remoto["por_ano"]:
        loc = local.get(r["ano"])
        bate = loc is not None and all(r[m] == int(loc[LOCAL.get(m, m)]) for m in MEDIDAS)
        linhas.append({"ano": r["ano"], **{m: r[m] for m in MEDIDAS}, "bate_com_local": bate})
    total_remoto = sum(r["ocorrencias"] for r in linhas)
    ok = (set(local) == {r["ano"] for r in linhas}
          and all(r["bate_com_local"] for r in linhas)
          and remoto["linhas_bronze_vigente"] == total_remoto)

    with open(resultados / "fase1_conferencia_databricks.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    print(f"bronze vigente no Databricks: {remoto['linhas_bronze_vigente']} linhas; "
          f"silver: {total_remoto}; bate com local: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
