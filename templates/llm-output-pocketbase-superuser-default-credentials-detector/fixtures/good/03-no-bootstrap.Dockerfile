FROM alpine:3.20
WORKDIR /pb
COPY pocketbase /pb/pocketbase
# No automatic admin bootstrap; operator runs `pocketbase superuser`
# manually inside the container after first deploy.
EXPOSE 8090
CMD ["/pb/pocketbase", "serve", "--http=0.0.0.0:8090"]
