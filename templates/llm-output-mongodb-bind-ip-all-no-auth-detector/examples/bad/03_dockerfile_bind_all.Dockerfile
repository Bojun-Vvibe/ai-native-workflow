FROM mongo:7.0

EXPOSE 27017

# Skips the official entrypoint's auth bootstrap and binds every interface.
CMD ["mongod", "--bind_ip_all", "--dbpath", "/data/db"]
