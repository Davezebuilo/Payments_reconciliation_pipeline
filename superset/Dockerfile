FROM apache/superset:6.1.0

# The image ships without database drivers; add the one for Postgres.
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary
USER superset

COPY --chmod=755 superset/start.sh /app/start.sh
CMD ["/app/start.sh"]