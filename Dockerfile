# Stage 1: Build React frontend
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python app
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm kubectl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY src/ src/
COPY config.yaml .
COPY --from=frontend-build /frontend/dist frontend/dist

# Include target service source for code analysis/fix
COPY target-source/ /workspace/data-pipeline-service/
RUN cd /workspace/data-pipeline-service && \
    git init && git add -A && \
    git -c user.email="agent@atdev.ai" -c user.name="Error Log Agent" \
    commit -m "Initial: data-pipeline-service source"

EXPOSE 8000

CMD ["uvicorn", "src.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
