FROM python:3.13-slim

WORKDIR /app

# Minimal smoke-test image. We only read public market data, so no signing
# SDK or env loader is needed yet. Re-add py-clob-client-v2 + python-dotenv
# when we go back to placing real orders.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY market.py gamma.py filters.py analyst.py ledger.py repo.py ./

CMD ["python", "analyst.py"]
