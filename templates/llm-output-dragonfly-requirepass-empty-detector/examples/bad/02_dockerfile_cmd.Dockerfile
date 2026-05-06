FROM docker.dragonflydb.io/dragonflydb/dragonfly:v1.21.0
EXPOSE 6379
CMD ["dragonfly", "--bind", "0.0.0.0", "--port", "6379"]
