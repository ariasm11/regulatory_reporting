FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# Only the runtime, reviewed rules and synthetic sample enter the image.
COPY siter/ ./siter/
COPY config/ ./config/
COPY sql/ ./sql/
COPY web/ ./web/
COPY data/sample/ ./data/sample/
EXPOSE 10000
STOPSIGNAL SIGTERM
CMD ["python", "-m", "siter.hosted"]
