FROM python:3.13-slim

WORKDIR /app

# Minimal smoke-test image. We only read public market data, so no signing
# SDK or env loader is needed yet. Re-add py-clob-client-v2 + python-dotenv
# when we go back to placing real orders.
RUN pip install --no-cache-dir \
    "httpx>=0.27" \
    "anthropic>=0.40" \
    "python-dotenv>=1.0"

COPY market.py gamma.py analyst.py ./

CMD ["python", "analyst.py"]
