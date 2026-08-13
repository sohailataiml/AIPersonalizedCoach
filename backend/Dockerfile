FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
RUN pip install --no-cache-dir -e backend

COPY backend backend
COPY data data
COPY scripts scripts
# The System Quality dashboard reads the latest measured evaluation run. It is
# a build artifact produced by `make eval`, shipped with the image rather than
# recomputed at startup - 71 cases on every boot would be startup fragility in
# exchange for a number that is already known.
COPY artifacts artifacts

EXPOSE 8000
# Explicit: no reliance on the working directory, shell state or an activated
# virtualenv. PYTHONPATH is set above.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
