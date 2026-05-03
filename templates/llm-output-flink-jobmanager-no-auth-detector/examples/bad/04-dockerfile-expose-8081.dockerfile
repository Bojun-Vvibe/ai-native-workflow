# Dockerfile.flink -- LLM-suggested image
# Exposes JobManager REST/UI port without front-proxy.
FROM flink:1.19.0-scala_2.12-java17

# Use the unified config introduced in Flink 1.19.
COPY config.yaml /opt/flink/conf/config.yaml

# Bind REST to all interfaces so the dashboard works from outside.
ENV FLINK_PROPERTIES="jobmanager.rpc.address: 0.0.0.0\nrest.bind-address: 0.0.0.0\ntaskmanager.numberOfTaskSlots: 4\n"

EXPOSE 6123 8081

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["jobmanager"]
