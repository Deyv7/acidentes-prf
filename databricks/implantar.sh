#!/usr/bin/env bash
# Sobe o código e os dados para o Databricks, roda bronze, silver e gold e
# compara o resultado com a execução local (resultados/fase1_* e fase2_*).
#
# Uso: databricks/implantar.sh <perfil-da-cli> <pasta-com-os-zips>
# A pasta deve ter ocorrencia_<ano>/ocorrencia_<ano>.zip (como em src/validar_fonte.py).
# A CLI é "databricks" no PATH, ou o caminho em DATABRICKS_CLI.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash no Windows: não converter /Workspace e /Volumes

PERFIL="$1"; DADOS="$2"
DB="${DATABRICKS_CLI:-databricks}"
cd "$(dirname "$0")/.."            # raiz do repositório
mkdir -p dist                      # arquivos temporários ficam aqui (ignorado pelo git)

USUARIO=$("$DB" current-user me -p "$PERFIL" -o json | python -c "import json,sys;print(json.load(sys.stdin)['userName'])")
W="/Workspace/Users/$USUARIO/acidentes-prf/notebooks"
V="dbfs:/Volumes/portfolio/acidentes_prf"

# 1. notebooks (só eles: o código vai como wheel, ver docs/explicacao.md)
"$DB" workspace mkdirs "$W" -p "$PERFIL"
for n in 00_configurar 01_bronze 02_silver 03_gold; do
  "$DB" workspace import "$W/$n" --file "notebooks/$n.py" --format SOURCE --language PYTHON --overwrite -p "$PERFIL"
done

# 2. schema e volumes
cat > dist/job00.json <<JSON
{"run_name": "acidentes-prf 00_configurar",
 "tasks": [{"task_key": "configurar", "notebook_task": {"notebook_path": "$W/00_configurar"}}]}
JSON
"$DB" jobs submit --json @dist/job00.json -p "$PERFIL" --timeout 20m > /dev/null

# 3. wheel com src/ e ZIPs de 2017 a 2025
rm -f dist/*.whl && python -m pip wheel . --no-deps -w dist -q
"$DB" fs cp dist/acidentes_prf-0.1.0-py3-none-any.whl "$V/artefatos/" --overwrite -p "$PERFIL"
for ano in $(seq 2017 2025); do
  "$DB" fs cp "$DADOS/ocorrencia_$ano/ocorrencia_$ano.zip" "$V/bruto/zips/datatran$ano.zip" --overwrite -p "$PERFIL"
done

# 4. bronze, silver e gold
sed "s#/Workspace/Users/SEU_USUARIO/acidentes-prf/notebooks#$W#" databricks/job_pipeline.json > dist/job12.json
"$DB" jobs submit --json @dist/job12.json -p "$PERFIL" --timeout 30m -o json > dist/execucao.json

# 5. saída das tarefas silver e gold -> resultados/fase{1,2}_conferencia_databricks.csv
for tarefa in silver gold; do
  RUN=$(python -c "import json;r=json.load(open('dist/execucao.json'));print([t['run_id'] for t in r['tasks'] if t['task_key']=='$tarefa'][0])")
  "$DB" jobs get-run-output "$RUN" -p "$PERFIL" -o json > "dist/saida_$tarefa.json"
done
python -I src/conferir_databricks.py dist/saida_silver.json dist/saida_gold.json resultados
