# Universo IA - Dockerfile de Execução em Contêiner Isolado
FROM python:3.11-slim

WORKDIR /app

# Instalação de dependências de compilação mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia de requisitos e instalação de pacotes Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia dos arquivos da aplicação
COPY server.py /app/
COPY static/ /app/static/
COPY tests/ /app/tests/

# Variáveis de ambiente
ENV PORT=8765 \
    HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

EXPOSE 8765

# Execução do servidor web
CMD ["python", "server.py"]
