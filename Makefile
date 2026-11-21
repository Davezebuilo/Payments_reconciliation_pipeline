include .env

START ?= 2026-10-01
DAYS ?= 30

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

.PHONY: up down reset logs psql data test