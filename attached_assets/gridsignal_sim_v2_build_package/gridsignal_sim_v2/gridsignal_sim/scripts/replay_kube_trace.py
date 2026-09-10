"""Replay Alibaba-style Kubernetes node/pod CSV traces offline.

Run from the ``gridsignal_sim`` project directory:

    PYTHONPATH=. python -m scripts.replay_kube_trace \
        --nodes openb_node_list_default.csv \
        --pods openb_pod_list_default.csv \
        --output kube-trace-report.json
"""

from __future__ import annotations

from runtime.kube_trace_replay import main


if __name__ == "__main__":
    raise SystemExit(main())