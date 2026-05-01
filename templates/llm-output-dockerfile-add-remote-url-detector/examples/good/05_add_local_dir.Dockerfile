FROM debian:stable-slim
# Pure local source, multi-line.
ADD \
  ./src/ \
  /app/src/
