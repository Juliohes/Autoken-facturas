FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# PaddleX importa OpenCV no-headless aunque el servicio no renderice nada.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY services/ocr-layout-paddle/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# La variante estructural se construye explícitamente con
# `--build-arg PADDLE_INSTALL_STRUCTURE=1`; el perfil ligero no arrastra sus modelos.
ARG PADDLE_INSTALL_STRUCTURE=0
COPY services/ocr-layout-paddle/requirements-structure.txt ./requirements-structure.txt
RUN if [ "$PADDLE_INSTALL_STRUCTURE" = "1" ]; then pip install -r requirements-structure.txt; fi

ENV PYTHONPATH=/app/src
RUN mkdir -p /app/src/ocr
COPY backend/src/ocr/__init__.py /app/src/ocr/__init__.py
COPY backend/src/ocr/extraction.py /app/src/ocr/extraction.py
COPY backend/src/ocr/layout.py /app/src/ocr/layout.py
COPY backend/src/ocr/layout_service.py /app/src/ocr/layout_service.py
COPY backend/src/ocr/layout_challengers.py /app/src/ocr/layout_challengers.py
COPY services/ocr-layout-paddle/service.py ./service.py

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8101
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8101"]
