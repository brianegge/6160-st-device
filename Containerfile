FROM python:3.12-slim

RUN groupadd -g 20 dialout-host || true

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

RUN useradd --system --no-create-home --groups dialout keypad

USER keypad

ENTRYPOINT ["keypad6160"]
