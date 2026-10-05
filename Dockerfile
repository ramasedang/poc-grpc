FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# iputils-ping so the command-injection lab has a real `ping` to abuse.
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Generate gRPC stubs into the image (server.py inits the DB itself at runtime).
RUN python -m grpc_tools.protoc -I protos \
        --python_out=. --grpc_python_out=. protos/shipping.proto

EXPOSE 50051 8000

# Overridden per-service by docker-compose (server.py / web.py).
CMD ["python", "server.py"]
