# SQL Server (pyodbc) — Debian 12 tabanlı resmi Python imajı + ODBC Driver 18
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL -o /tmp/packages-microsoft-prod.deb \
        https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && (dpkg -i /tmp/packages-microsoft-prod.deb || apt-get -fy install) \
    && rm -f /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && rm -rf /var/lib/apt/lists/*

# Kurum içi LLM uçlarının (*.gpudtx.kuveytturk.com.tr) kök CA'sı; sistem güven deposuna eklenir.
COPY certs/corporate-inference-root.crt /usr/local/share/ca-certificates/corporate-inference-root.crt
RUN update-ca-certificates
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
