FROM krakend:2.6
COPY krakend.json /etc/krakend/krakend.json
EXPOSE 8080
CMD ["krakend", "run", "-c", "/etc/krakend/krakend.json"]
