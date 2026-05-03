# Single-node VictoriaMetrics on a public listen addr, no auth.
FROM victoriametrics/victoria-metrics:v1.96.0
EXPOSE 8428
ENTRYPOINT ["/victoria-metrics-prod", "-httpListenAddr=:8428", "-storageDataPath=/vmdata", "-retentionPeriod=12"]
