FROM python:3.13-slim-bookworm AS dependencies
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake swig pkg-config libxml2-dev libbz2-dev zlib1g-dev libglpk-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv
COPY requirements.txt requirements-optional.txt /build/
RUN pip install --no-cache-dir --prefer-binary -r /build/requirements.txt -r /build/requirements-optional.txt

FROM python:3.13-slim-bookworm
ARG VCS_REF=development
LABEL org.opencontainers.image.source="https://github.com/matthew169169/aivc"
LABEL org.opencontainers.image.revision=$VCS_REF
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OMICS_GEM_HOST=0.0.0.0 OMICS_GEM_PORT=8765 OMICS_GEM_DATA_DIR=/data \
    OMICS_GEM_JOB_MODE=background OMICS_GEM_VERSION=$VCS_REF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libexpat1 libgomp1 libglpk40 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 studio && useradd --uid 10001 --gid studio --create-home studio \
    && mkdir -p /app /data && chown studio:studio /app /data
COPY --from=dependencies --chown=studio:studio /opt/venv /opt/venv
WORKDIR /app
COPY --chown=studio:studio . .
USER studio
RUN python -c "import cobra, libsbml, swiglpk, openpyxl, xlrd"
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/api/health', timeout=4).read()"
CMD ["python", "run_local.py"]
