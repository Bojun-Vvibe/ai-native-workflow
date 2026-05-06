FROM docker.dragonflydb.io/dragonflydb/dragonfly:v1.21.0
EXPOSE 6379
CMD ["dragonfly", "--port", "6379", "--requirepass", "kP9$mLq2Wn7vRb5Xc8Tj"]
