# Single-node VictoriaMetrics with basic auth.
FROM victoriametrics/victoria-metrics:v1.96.0
EXPOSE 8428
ENTRYPOINT ["/victoria-metrics-prod", \
            "-httpListenAddr=:8428", \
            "-httpAuth.username=ops", \
            "-httpAuth.password=${VM_PASS}", \
            "-storageDataPath=/vmdata"]
