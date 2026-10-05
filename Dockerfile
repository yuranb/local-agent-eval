# API container (scope item 8). Never built on the dev machine — Docker is
# not installed there (see STATUS.md, "未验证").
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# The container has no Ollama inside; point OLLAMA_HOST at the host machine's
# Ollama server. On Docker Desktop (macOS/Windows) host.docker.internal works;
# on Linux add --add-host=host.docker.internal:host-gateway.
ENV OLLAMA_HOST=http://host.docker.internal:11434

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
