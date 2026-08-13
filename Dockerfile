FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY api ./api
COPY web ./web
COPY docs ./docs
COPY tests ./tests

RUN pip install --no-cache-dir pydantic
ENV PYTHONPATH=/app/src
EXPOSE 8000 5173
CMD ["python", "-m", "api.simple_server"]
