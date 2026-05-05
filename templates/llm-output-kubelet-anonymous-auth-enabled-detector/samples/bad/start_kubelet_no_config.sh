# Shell snippet starting kubelet directly with no --config, no
# --anonymous-auth=false, and no --kubeconfig pointing at a policy file.
# The kubelet binary's compiled-in default for anonymous-auth is true
# when no config is supplied, so this is unsafe to ship as-is.
#!/bin/sh
exec /usr/bin/kubelet \
  --hostname-override=node-01 \
  --container-runtime-endpoint=unix:///run/containerd/containerd.sock \
  --pod-manifest-path=/etc/kubernetes/manifests
