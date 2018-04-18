generate traffic:
  junos.rpc:
    - name: ping
    - rapid: True
    - host: 10.1.0.10
    - count: "300"

