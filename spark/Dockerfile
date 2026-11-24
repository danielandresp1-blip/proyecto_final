ARG SPARK_IMAGE=apache/spark:3.5.3-scala2.12-java17-python3-ubuntu
FROM ${SPARK_IMAGE}

ARG SPARK_SNOWFLAKE_PACKAGES=net.snowflake:spark-snowflake_2.12:3.1.2
ENV SPARK_SNOWFLAKE_PACKAGES=${SPARK_SNOWFLAKE_PACKAGES} \
    SPARK_IVY_DIR=/opt/ivy \
    PATH=/opt/spark/bin:${PATH}

USER root
RUN mkdir -p /opt/spark-apps ${SPARK_IVY_DIR} && chown -R spark:spark /opt/spark-apps ${SPARK_IVY_DIR}
COPY --chown=spark:spark jobs/ /opt/spark-apps/
COPY --chown=spark:spark run_obt.sh /opt/spark-apps/run_obt.sh
RUN chmod +x /opt/spark-apps/run_obt.sh
USER spark

# Precarga el conector de Snowflake (y su driver JDBC) en la cache de Ivy durante el build,
# para que cada ejecucion orquestada por Kestra no tenga que descargarlo de nuevo.
RUN echo "print('warm-up')" > /tmp/warmup.py \
 && spark-submit --master "local[1]" --packages "${SPARK_SNOWFLAKE_PACKAGES}" \
      --conf spark.jars.ivy="${SPARK_IVY_DIR}" /tmp/warmup.py \
 && rm /tmp/warmup.py

WORKDIR /opt/spark-apps
ENTRYPOINT []
