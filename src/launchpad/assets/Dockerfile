FROM python:3.12.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY --chown=10001:10001 service /app/service
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "service.app"]
