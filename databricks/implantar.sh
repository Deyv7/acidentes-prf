#!/usr/bin/env bash
# Sobe o código e os dados para o Databricks e roda bronze e silver.
# Uso: databricks/implantar.sh <perfil-da-cli> <pasta-com-os-zips>
# A pasta deve ter ocorrencia_<ano>/ocorrencia_<ano>.zip (como em src/validar_fonte.py).
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash no Windows: não converter /Workspace e /Volumes

PERFIL="$1"; DADOS="$2"
USUARIO=$(databricks current-user me -p "$PERFIL" -o json | python -c "import json,sys;print(json.load(sys.stdin)['userName'])")
W="/Workspace/Users/$USUARIO/acidentes-prf/notebooks"
V="dbfs:/Volumes/portfolio/acidentes_prf"

# 1. notebooks (só eles: o código vai como wheel, ver docs/explicacao.md)
databricks workspace mkdirs "$W" -p "$PERFIL"
for n in 00_configurar 01_bronze 02_silver; do
  databricks workspace import "$W/$n" --file "notebooks/$n.py" --format SOURCE --language PYTHON --overwrite -p "$PERFIL"
done

# 2. schema e volumes
cat > /tmp/job00.json <<JSON
{"run_name": "acidentes-prf 00_configurar",
 "tasks": [{"task_key": "configurar", "notebook_task": {"notebook_path": "$W/00_configurar"}}]}
JSON
databricks jobs submit --json @/tmp/job00.json -p "$PERFIL" --timeout 20m > /dev/null

# 3. wheel com src/ e ZIPs de 2017 a 2025
rm -rf dist && python -m pip wheel . --no-deps -w dist -q
databricks fs cp dist/acidentes_prf-0.1.0-py3-none-any.whl "$V/artefatos/" --overwrite -p "$PERFIL"
for ano in $(seq 2017 2025); do
  databricks fs cp "$DADOS/ocorrencia_$ano/ocorrencia_$ano.zip" "$V/bruto/zips/datatran$ano.zip" --overwrite -p "$PERFIL"
done

# 4. bronze e silver
sed "s#/Workspace/Users/SEU_USUARIO/acidentes-prf/notebooks#$W#" databricks/job_bronze_silver.json > /tmp/job12.json
databricks jobs submit --json @/tmp/job12.json -p "$PERFIL" --timeout 30m
