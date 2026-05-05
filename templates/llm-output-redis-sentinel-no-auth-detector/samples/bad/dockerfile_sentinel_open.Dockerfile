FROM redis:7-alpine
EXPOSE 26379
# Run Sentinel listening on every interface, no auth, protected-mode off
# so the orchestrator's health probe can reach it.
CMD ["redis-sentinel", "/etc/redis/sentinel.conf", "--bind", "0.0.0.0", "--protected-mode", "no"]
