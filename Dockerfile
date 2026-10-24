FROM python:3.12-slim

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir "poetry>=2,<3"
COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
RUN poetry install --only main
COPY . .
EXPOSE 8501
CMD ["poetry", "run", "dashboard"]