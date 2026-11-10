#!/usr/bin/env bash
# Levanta el túnel SOCKS en 127.0.0.1:9090 encadenando 3 VPS:
#   Kali → root@111.90.148.187 → root@111.90.147.110 → root@111.90.147.197
# Usado por proxychains4.conf (entrada `socks5 127.0.0.1 9090`).
#
# Idempotente: mata cualquier ssh previo apuntando a :9090, reabre el túnel
# y verifica que el puerto quede escuchando.

set -uo pipefail

KEY="$HOME/.ssh/id_ed25519_anon"
LOG="/tmp/ssh_tunnel.log"

if [ ! -f "$KEY" ]; then
    echo "[!] No existe $KEY — corre setup_anon_chain.sh para generarla y desplegarla." >&2
    exit 2
fi

pkill -9 -f "ssh.*9090" 2>/dev/null || true
rm -f "$LOG"

ssh -fNT \
  -i "$KEY" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o StdinNull=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -D 127.0.0.1:9090 \
  -p 20203 \
  -o ProxyCommand="ssh -T -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -p 20203 -W %h:%p root@111.90.147.110" \
  root@111.90.147.197 \
  2>"$LOG"

# Pequeña espera para que el listener aparezca.
for i in 1 2 3 4 5; do
    if ss -tlnp 2>/dev/null | grep -q ":9090 "; then
        echo "[+] Túnel SOCKS arriba en 127.0.0.1:9090"
        exit 0
    fi
    sleep 0.5
done

echo "[-] El túnel no levantó. Log:" >&2
cat "$LOG" >&2 || true
exit 1
