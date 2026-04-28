FROM python:latest
RUN pip install requests

# implicit-latest below
FROM alpine
RUN apk add --no-cache curl

# multi-stage with explicit :latest plus alias
FROM node:latest AS builder
WORKDIR /src
COPY . .
RUN npm ci && npm run build

FROM nginx:1.27-alpine
COPY --from=builder /src/dist /usr/share/nginx/html
