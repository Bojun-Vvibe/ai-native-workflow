# Shell snippet that points kubelet at an external --config file. The
# detector defers to the file-based rules and does not flag the
# invocation by itself.
#!/bin/sh
exec /usr/bin/kubelet \
  --config=/var/lib/kubelet/config.yaml \
  --kubeconfig=/etc/kubernetes/kubelet.conf \
  --container-runtime-endpoint=unix:///run/containerd/containerd.sock
