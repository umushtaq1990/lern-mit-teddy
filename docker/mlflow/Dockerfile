FROM python:3.12-slim
WORKDIR /app
# Pinned to match the mlflow version in pyproject.toml's dev dependency group
# (src/langgraph/eval/run_eval.py logs to this server via the mlflow client).
RUN pip install --no-cache-dir mlflow==3.18.0
EXPOSE 5000
# SQLite backend — single local user, no need to coordinate with the app's
# Postgres DB. Artifacts land on the mounted volume (see docker-compose.yml).
# --allowed-hosts: MLflow 3.x rejects requests whose Host header isn't
# allow-listed — both the in-network service name (mlflow:5000) and the
# docker-compose host-mapped port (localhost:5001, see docker-compose.yml)
# must be listed, not just the container's own internal port.
CMD mlflow server \
    --backend-store-uri sqlite:////mlflow-data/mlflow.db \
    --default-artifact-root /mlflow-data/artifacts \
    --host 0.0.0.0 --port 5000 \
    --allowed-hosts "mlflow,mlflow:5000,localhost,localhost:5000,localhost:5001"
