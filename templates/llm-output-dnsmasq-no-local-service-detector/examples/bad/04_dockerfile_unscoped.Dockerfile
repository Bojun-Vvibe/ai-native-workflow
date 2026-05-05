FROM alpine:3.19
RUN apk add --no-cache dnsmasq
EXPOSE 53/udp
CMD ["dnsmasq", "-k", "--server=9.9.9.9", "--cache-size=500"]
