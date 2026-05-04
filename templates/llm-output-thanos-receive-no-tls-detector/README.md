# llm-output-thanos-receive-no-tls-detector

Stdlib-Python detector that flags Thanos Receive / remote-write
configurations emitted by an LLM where TLS is disabled, missing, or
defeated on the gRPC remote-write path.

## Why this exists

Thanos Receive terminates Prometheus `remote_write` traffic from many
producers (often from many tenants). Upstream's "minimal" examples
omit `--grpc-server-tls-cert*` flags. LLMs replicate that minimal
shape, then expose the resulting deployment on `LoadBalancer` /
`NodePort` / `0.0.0.0`. The result: every sample on the wire is
cleartext, and any reachable client can write to any tenant.

The detector flags four orthogonal regressions:

1. `thanos receive` invocation with non-loopback `--grpc-address` and
   no `--grpc-server-tls-cert` flag.
2. `--grpc-server-tls-cert=""` (explicit empty string defeating
   presence checks).
3. Helm values: `receive.tls.enabled: false` while
   `receive.service.type` is `LoadBalancer` or `NodePort`.
4. Prometheus `remote_write.url:` pointing at a non-loopback host
   over `http://` (cleartext scheme).

CWE refs: CWE-319, CWE-306.

Suppression: a top-level `# thanos-no-tls-allowed` comment in the
file disables all rules (use only for local dev fixtures).

## API

```python
from detector import scan
findings = scan(open("config.yaml").read())
# findings is a list of (line_number, reason) tuples; empty == clean.
```

CLI:

```
python3 detector.py path/to/config.yaml [more.yaml ...]
```

Exit code = number of files with at least one finding.

## Layout

```
detector.py                # the rule engine (stdlib only)
run_example.py             # worked example, runs all bundled samples
examples/
  bad_1_no_tls_flags.txt   # cli without --grpc-server-tls-cert
  bad_2_empty_cert.txt     # --grpc-server-tls-cert=""
  bad_3_helm_lb_no_tls.txt # helm values: tls.enabled=false + LB
  bad_4_remote_write_http.txt  # remote_write http:// to public host
  good_1_full_mtls.txt     # cert + key + client-ca all set
  good_2_loopback_only.txt # bound to 127.0.0.1
  good_3_helm_cluster_tls.txt  # ClusterIP + tls.enabled: true
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_no_tls_flags.txt: FLAG (1 finding(s))
    L1: thanos receive exposes --grpc-address=0.0.0.0:10901 without --grpc-server-tls-cert (cleartext gRPC remote-write)
  bad_2_empty_cert.txt: FLAG (1 finding(s))
    L4: --grpc-server-tls-cert is set to empty string (TLS effectively disabled)
  bad_3_helm_lb_no_tls.txt: FLAG (2 finding(s))
    L1: thanos receive exposes --grpc-address=0.0.0.0:10901 without --grpc-server-tls-cert (cleartext gRPC remote-write)
    L7: receive.tls.enabled=false while receive.service.type=LoadBalancer (publicly reachable cleartext gRPC) — see line 4
  bad_4_remote_write_http.txt: FLAG (1 finding(s))
    L1: thanos receive exposes --grpc-address=0.0.0.0:10901 without --grpc-server-tls-cert (cleartext gRPC remote-write)

== good samples (should each produce 0 findings) ==
  good_1_full_mtls.txt: ok (0 finding(s))
  good_2_loopback_only.txt: ok (0 finding(s))
  good_3_helm_cluster_tls.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/3
RESULT: PASS
```

## Limitations

- Regex-based; assumes flag style consumed by the official Thanos
  binary. Custom wrappers that translate env-vars to flags need to
  be expanded into the rendered command line first.
- Helm rule is intentionally narrow: it only fires when the receive
  service type is `LoadBalancer` or `NodePort`. Operators using
  `ClusterIP` + Ingress-level TLS termination should add an explicit
  `# thanos-no-tls-allowed` if they keep gRPC plain inside-cluster.
- The detector is local-only: it does not resolve template values,
  pull secrets, or talk to the cluster.
