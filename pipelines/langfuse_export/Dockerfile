FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# pymssql bundles FreeTDS, so no Microsoft ODBC driver / apt repo dance needed.
# git is needed for pip to install the ai-platform-shared dependency from GitHub.
RUN apt-get update && apt-get install -y --no-install-recommends gcc freetds-dev git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY export.py ./

CMD ["python", "export.py"]
