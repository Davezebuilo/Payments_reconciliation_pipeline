"""Each day: load that day's files, rebuild and test every model, and on the last day grade the result."""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

VENV = "/home/airflow/recon-venv/bin"

with DAG(
    dag_id="recon_daily",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
    end_date=datetime(2026, 11, 4),  # the last day with files in data/landing
    catchup=True,                    # run every day since start_date, not just today
    max_active_runs=1,               # each run rebuilds every model, so runs must not overlap
    default_args={"cwd": "/opt/recon", "retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["recon"],
) as dag:
    load = BashOperator(
        task_id="load",
        bash_command=VENV + "/python -m loader.load --date {{ ds }}",
    )

    build = BashOperator(
        task_id="dbt_build",
        bash_command=VENV + "/dbt --no-use-colors build --project-dir dbt/recon --profiles-dir dbt/recon",
    )

    # Grading needs every day loaded, so it only runs on the last day. Exit code 99 marks it skipped.
    grade = BashOperator(
        task_id="grade",
        bash_command='[ "{{ ds }}" = "{{ dag.end_date | ds }}" ] || exit 99; ' + VENV + "/python -m grader.grade",
        skip_on_exit_code=99,
        retries=0,
    )

    load >> build >> grade