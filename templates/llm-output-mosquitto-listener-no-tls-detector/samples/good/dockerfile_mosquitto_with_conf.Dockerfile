FROM eclipse-mosquitto:2
EXPOSE 8883
COPY mosquitto.conf /mosquitto/config/mosquitto.conf
COPY certs/ /mosquitto/certs/
# Pass an explicit -c so the config above (TLS-only listener on 8883) is used.
CMD ["mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
