FROM krakend:2.6
COPY krakend.json /etc/krakend/krakend.json
EXPOSE 8080
# --debug toggles the /__debug/ endpoint at runtime.
CMD ["krakend", "run", "-c", "/etc/krakend/krakend.json", "--debug"]
