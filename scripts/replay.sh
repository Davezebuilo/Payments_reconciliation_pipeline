#!/usr/bin/env bash
# Prove incremental builds give the same answer as a full rebuild.
# Replays every landing day like Airflow does (load one day, incremental dbt build), grades the result,
# then rebuilds from scratch and compares the two fact tables row by row.
# WARNING: it empties the warehouse first. Everything is reloaded from data/landing, so nothing is lost.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
PSQL="docker compose exec -T warehouse psql -U $POSTGRES_USER -d $POSTGRES_DB -q -v ON_ERROR_STOP=1"
DBT="cd dbt/recon && DBT_PROFILES_DIR=. ../../.venv/bin/dbt"

$PSQL -c "drop schema if exists staging cascade; drop schema if exists intermediate cascade;
          drop schema if exists marts cascade;
          truncate raw.ledger, raw.processor_settlement, raw.biller_vends, raw.load_log;"

for day in $(ls data/landing); do
  .venv/bin/python -m loader.load --date "$day" > /dev/null
  start=$(date +%s)
  (eval "$DBT build --quiet")
  echo "$day built in $(( $(date +%s) - start ))s"
done

echo "Grade of the incremental build:"
.venv/bin/python -m grader.grade | tail -2 || true

$PSQL -c "drop table if exists perf.fct_incremental;
          create table perf.fct_incremental as select * from marts.fct_reconciliation;"
(eval "$DBT build --full-refresh --quiet")
$PSQL -c "select
  (select count(*) from (select * from perf.fct_incremental except select * from marts.fct_reconciliation) a) as only_in_incremental,
  (select count(*) from (select * from marts.fct_reconciliation except select * from perf.fct_incremental) b) as only_in_full_refresh;"