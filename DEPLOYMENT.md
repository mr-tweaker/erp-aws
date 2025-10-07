## Deployment & Operations Guide

This guide covers provisioning, configuration, access, operations, and recovery for the ERP sync system.

### 1. Provisioning (AWS Console or CLI)
- Launch two Ubuntu 22.04 EC2 instances (Branch‑A, Branch‑B) in the same VPC.
- Security Group inbound:
  - SSH 22: your IP (/32)
  - HTTP 80: 0.0.0.0/0
  - HTTPS 443: 0.0.0.0/0
  - PostgreSQL 5432: source = the same SG (intra‑SG)
  - SSH 22: source = the same SG (intra‑SG) for inter‑branch SSH/scp
- Allocate an Elastic IP and associate to Branch‑A for a fixed public address.
- Optional but recommended: attach IAM role with `AmazonSSMManagedInstanceCore` to both instances for emergency access (Session Manager).

### 2. System Setup (on each instance)
- Install packages: PostgreSQL, OpenSSL, awscli, mailutils, netcat, Nginx, Python3 venv.
- Create `/etc/erp_sync.env` with:
```
ERP_ENCRYPT_PASSPHRASE=<same-on-both>
ERP_DB_USER=erp_sync
ERP_DB_PASS=<same-on-both>
ERP_DB_NAME=erpdb
ERP_REMOTE_DB_HOST=<peer-private-ip>
ERP_ALERT_EMAIL=
ERP_S3_BUCKET=s3://<your-bucket>
AWS_DEFAULT_REGION=us-east-1
```
- Place scripts under `/opt/erp` and `chmod 750` (decrypt script must be executable on both nodes).
- Configure PostgreSQL:
  - `listen_addresses = '*'`
  - `pg_hba.conf`: allow md5 from peer private IP for `erp_sync` on `erpdb`.
  - Create DB, tables (`inventory`, `sales`, `sync_logs`), role `erp_sync`, grant privileges.

### 3. Sync & Cron
- Main orchestrator: `/opt/erp/sync_erp.sh` (bidirectional push/pull, AES‑256‑CBC, SCP, sequence resets).
- Cron (`/etc/cron.d/erp_sync`):
  - */5 sync, */2 health, 02:00 backup, weekly cleanup. Ensure each job sources `/etc/erp_sync.env`.

### 4. Monitoring Dashboard
- App at `/opt/erp/dashboard/app.py`, Gunicorn service `erp-dashboard.service` binds 0.0.0.0:8080.
- Nginx proxies 443→8080 (self‑signed TLS). Access `https://<ElasticIP>/`.

### 5. Backups
- Daily `backup_to_s3.sh`: pg_dump → gzip → OpenSSL enc → S3; retention keep last 7.
- Restore with `recover_from_backup.sh -k <s3_key>`.

### 6. Security Hardening
- UFW on each node:
  - `ufw allow from <your-ip> to any port 22 proto tcp`
  - `ufw allow 80,443/tcp`
  - `ufw allow from <peer-private-ip> to any port 22 proto tcp`
  - `ufw allow from <peer-private-ip> to any port 5432 proto tcp`
- SSH key-based only; keep `PasswordAuthentication no` in `sshd_config`.
- Keep SSM role for emergency; remove broad SG rules after testing.

### 7. Validation
```bash
# Insert sample row and sync
sudo /opt/erp/test_sync.sh
# Dashboard health
curl -k https://<ElasticIP>/health
```

### 8. Operations
```bash
# Manual sync
sudo /opt/erp/sync_erp.sh
# Health check
sudo /opt/erp/health_check.sh
# Backup now
sudo /opt/erp/backup_to_s3.sh
# View logs
sudo tail -n 200 /var/log/erp_sync.log
```

### 9. Recovery Playbooks
- Remote psql prompting on Branch‑B:
  - Ensure remote SSH block in `sync_erp.sh` exports `PGPASSWORD` and uses `psql -h 127.0.0.1`.
- Decrypt permission denied on Branch‑B:
  - `sudo chmod 755 /opt/erp/decrypt_data.sh && sudo chown ubuntu:ubuntu /opt/erp/decrypt_data.sh`
- Locked out of SSH (UFW/SG):
  - Preferred: use AWS Systems Manager Session Manager; then re-add UFW rules and restart ssh.
  - Last resort: detach root volume, mount on helper, set `/etc/ufw/ufw.conf` to `ENABLED=no`, ensure `authorized_keys`, reattach and boot.
- Serial console passwordless access:
  - Use GRUB `systemd.unit=emergency.target`, then `passwd ubuntu`, fix UFW, reboot.

### 10. DNS (Optional)
- Create Route 53 A record to the Elastic IP. Replace self-signed cert with Let’s Encrypt for production.

