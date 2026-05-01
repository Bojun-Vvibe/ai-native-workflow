# Bad: explicit USER root, missing USER, and final-stage root via uid:gid.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y curl

# Explicit root — flagged twice (explicit + final).
USER root

COPY app.py /app/app.py
WORKDIR /app
CMD ["python", "app.py"]
