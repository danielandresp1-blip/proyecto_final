ARG DBT_IMAGE=ghcr.io/dbt-labs/dbt-snowflake:1.9.latest
FROM ${DBT_IMAGE}

WORKDIR /usr/app/dbt
COPY . /usr/app/dbt
RUN chmod +x /usr/app/dbt/run_dbt.sh

ENV DBT_PROFILES_DIR=/usr/app/dbt
# Sin entrypoint propio: Kestra ejecuta comandos de shell dentro del contenedor.
ENTRYPOINT []
CMD ["/usr/app/dbt/run_dbt.sh", "build"]
