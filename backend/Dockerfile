# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Backend image: Django + Celery + PySpark. The same image runs the web
# process, the Celery worker and Flower (command is overridden per service).
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm

# --- System deps: Java 17 (required by Spark 3.5) + build essentials ---
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        procps \
        curl \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# --- Non-root user ---
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# --- Python deps ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Pre-fetch Hadoop-AWS + AWS SDK jars so Spark can read from s3a:// ---
# PySpark 3.5.x ships Hadoop 3.3.4; match the hadoop-aws version exactly.
ARG HADOOP_AWS_VERSION=3.3.4
ARG AWS_SDK_VERSION=1.12.367
RUN SPARK_JARS="$(python -c 'import pyspark, os; print(os.path.join(os.path.dirname(pyspark.__file__), "jars"))')" && \
    curl -fsSL -o "${SPARK_JARS}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" \
        "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" && \
    curl -fsSL -o "${SPARK_JARS}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar" \
        "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar"

# --- App source ---
COPY . .
RUN mkdir -p /data/results && chown -R app:app /app /data

USER app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
