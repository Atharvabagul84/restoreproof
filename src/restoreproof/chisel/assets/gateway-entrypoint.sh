#!/bin/sh
set -eu
umask 077
openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/tls.key -out /tmp/tls.crt \
  -days 1 -subj '/CN=RestoreProof disposable Chisel' -addext 'subjectAltName=IP:127.0.0.1' >/dev/null 2>&1
exec nginx -g 'daemon off;'
