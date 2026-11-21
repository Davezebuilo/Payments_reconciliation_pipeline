include .env

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

.PHONY: up down reset logs psql