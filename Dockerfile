FROM python:3.12-slim

WORKDIR /app

# gosu lets the entrypoint drop from root to an unprivileged PUID:PGID at start.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# setuptools-scm derives the version from git tags, but the build context has no
# .git. The release workflow passes the version semantic-release computed; a
# local `docker build` without it falls back to 0.0.0.
ARG SETUPTOOLS_SCM_PRETEND_VERSION_FOR_WHITELISTARR=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_WHITELISTARR=$SETUPTOOLS_SCM_PRETEND_VERSION_FOR_WHITELISTARR

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV STATE_DB_PATH=/data/state.db \
    WEBHOOK_HOST=0.0.0.0 \
    WEBHOOK_PORT=8000 \
    PUID=1000 \
    PGID=1000

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').getcode()==200 else 1)"

# Runs as root, drops to PUID:PGID via gosu, then execs the app (CMD).
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["whitelistarr"]
