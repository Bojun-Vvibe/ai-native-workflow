FROM eclipse-mosquitto:2
EXPOSE 1883
# Run mosquitto on the cleartext MQTT port with no TLS material and no -c
# config file — the binary uses its bind-all default.
CMD ["mosquitto", "-p", "1883"]
