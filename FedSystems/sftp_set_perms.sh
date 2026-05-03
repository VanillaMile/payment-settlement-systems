#!/bin/bash
# sftp_set_perms.sh - set outbound as read-only
set -e

SFTP_ROOT="/home"

for d in "$SFTP_ROOT"/*; do
  [ -d "$d" ] || continue
  user=$(basename "$d")

  # Ensure chroot root ownership and permissions
  chown root:root "$d" || true
  chmod 755 "$d" || true

  outbound="$d/outbound"


  if [ -d "$outbound" ]; then
    # owner read+execute, no write => user can read/list but not create
    chown "$user:$user" "$outbound" || true
    chmod 500 "$outbound" || true
  fi

done

echo "SFTP permissions applied"
