ARG NODE_VERSION=20.11.1
FROM --platform=linux/amd64 python:3.12.3-slim AS base
RUN pip install --no-cache-dir requests==2.32.3

FROM node:${NODE_VERSION}-bookworm-slim AS builder
WORKDIR /src
COPY . .
RUN npm ci && npm run build

FROM nginx@sha256:9d6b58feebd2dbd3c56ab5853333d627cc6e281011cfd6050fa4bcf2072c9496
COPY --from=builder /src/dist /usr/share/nginx/html
