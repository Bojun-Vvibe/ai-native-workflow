FROM alpine:3.20
WORKDIR /pb
COPY pocketbase /pb/pocketbase
RUN /pb/pocketbase superuser create test@test.com password
EXPOSE 8090
CMD ["/pb/pocketbase", "serve", "--http=0.0.0.0:8090"]
