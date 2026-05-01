# Good: explicitly drops to a non-root user before CMD.
FROM python:3.12-slim

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY app.py /app/app.py
USER appuser
CMD ["python", "app.py"]
