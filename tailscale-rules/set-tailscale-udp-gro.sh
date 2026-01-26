#!/usr/bin/env bash

echo "setting tailscale-udp-gro"
NETDEV=$(ip -o route get 8.8.8.8 | cut -f 5 -d " ")
sudo ethtool -K $NETDEV rx-udp-gro-forwarding on rx-gro-list off
tailscale_udp_gro_status=$?
if [[ $tailscale_udp_gro_status -eq 0 ]]; then
  echo "success!"
else
  echo "failure!"
fi
