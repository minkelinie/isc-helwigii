FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels ".[ui]"

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ISC_HELWIGII_PROJECT=/data/research.db \
    ISC_HELWIGII_DB_PATH=/data/research.db \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels isc-helwigii[ui] \
    && groupadd -r researcher && useradd -r -g researcher researcher \
    && mkdir /data /app && chown researcher:researcher /data /app
COPY src/isc_helwigii/ui.py /app/launch.py
WORKDIR /app
USER researcher
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD isc-helwigii health --json || exit 1
CMD ["sh", "-c", "isc-helwigii init /data/research.db && exec python -m streamlit run /app/launch.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false"]
