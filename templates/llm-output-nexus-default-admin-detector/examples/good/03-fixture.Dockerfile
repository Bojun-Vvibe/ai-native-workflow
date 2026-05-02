# nexus-default-admin-allowed
# Disposable single-use CI fixture; the container is destroyed at end of job.
FROM sonatype/nexus3:3.70.0
ENV NEXUS_SECURITY_RANDOMPASSWORD=false
ENV NEXUS_SECURITY_INITIAL_PASSWORD=admin123
EXPOSE 8081
