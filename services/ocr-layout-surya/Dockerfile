FROM python:3.12-slim

ARG LLAMA_CPP_VERSION=b10566
ARG LLAMA_CPP_SHA256=0c34561d623299c113e46f9fdd97bff5b219b25554243a21a243aebc81253ea1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN pip install .

# El challenger es de laboratorio y debe poder ejecutarse sin GPU. Instalar primero las ruedas CPU
# evita que el resolvedor elija el runtime CUDA completo como dependencia de Surya.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.7,<3" \
    "torchvision>=0.20,<1"

# Surya 0.22 usa llama.cpp como backend CPU para el reconocimiento de página completa.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && curl --fail --silent --show-error --location \
        "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_VERSION}/llama-${LLAMA_CPP_VERSION}-bin-ubuntu-x64.tar.gz" \
        --output /tmp/llama.tar.gz \
    && echo "${LLAMA_CPP_SHA256}  /tmp/llama.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/llama.tar.gz -C /tmp \
    && mkdir -p /opt/llama \
    && cp -a "/tmp/llama-${LLAMA_CPP_VERSION}/." /opt/llama/ \
    && ln -s /opt/llama/llama-server /usr/local/bin/llama-server \
    && rm -rf /tmp/llama.tar.gz "/tmp/llama-${LLAMA_CPP_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

COPY services/ocr-layout-surya/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY services/ocr-layout-surya/service.py ./service.py

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8102
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8102"]
