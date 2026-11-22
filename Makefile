include .env
export

START ?= 2026-10-01
DAYS ?= 30

DBT = cd dbt/recon && DBT_PROFILES_DIR=. ../../.venv/bin/dbt

up:      ## start the warehouse
	docker compose up -d --wait

down:    ## stop it (data is kept)
	docker compose down

reset:   ## stop and DELETE all data, so init scripts run again
	docker compose down -v

logs:
	docker compose logs -f warehouse

psql:    ## open a SQL shell inside the container
	docker compose exec warehouse psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

data:    ## generate synthetic data into data/
	.venv/bin/python -m generator.generate --start $(START) --days $(DAYS)

test:
	.venv/bin/python -m pytest -q

load:      ## load every day in data/landing into raw
	.venv/bin/python -m loader.load --all

load-day:  ## reload one day: make load-day DATE=2026-10-02
	.venv/bin/python -m loader.load --date $(DATE)

dbt-debug:  ## check dbt can reach the warehouse
	$(DBT) debug

build:      ## run every model and test
	$(DBT) build

freshness:  ## warn if a source stopped arriving
	$(DBT) source freshness

docs:       ## browse the models and lineage at http://localhost:8080
	$(DBT) docs generate
	$(DBT) docs serve --port 8080

grade:      ## score the pipeline against the ground truth
	.venv/bin/python -m grader.grade

airflow-logs:  ## follow Airflow's log
	docker compose logs -f airflow

.PHONY: up down reset logs psql data test load load-day dbt-debug build freshness docs grade airflow-logs