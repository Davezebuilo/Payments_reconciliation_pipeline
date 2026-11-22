FROM apache/airflow:3.3.2-python3.12

# The pipeline gets its own virtualenv, so its packages (pandas, dbt...) can never clash with Airflow's.
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /home/airflow/recon-venv \
 && /home/airflow/recon-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt