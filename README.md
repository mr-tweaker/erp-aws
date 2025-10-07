## ERP Data Synchronization System (AWS EC2 + PostgreSQL + Bash)

A secure, demo-ready system that syncs ERP data between two AWS EC2 instances (Branch‑A ↔ Branch‑B) using PostgreSQL, OpenSSL encryption, SSH/SCP, cron jobs, S3 backups, and a Flask monitoring dashboard.

### Current Status
- Branch‑A and Branch‑B deployed on AWS EC2; bidirectional sync working
- Encrypted backups to S3 enabled; retention configured
- Dashboard service running behind Nginx TLS at https://44.222.20.243/
- Health OK: local/remote DB reachable; last sync within expected SLA
- UI supports Inventory CRUD (create/update/delete) on Branch‑A; Sales read-only list

### Access
- Dashboard HTTPS: https://44.222.20.243/
- Health JSON: https://44.222.20.243/health
- SSH to Branch‑A: `ssh -i /home/aniket/erp-demo-key.pem ubuntu@ec2-44-222-20-243.compute-1.amazonaws.com`

### Repository Layout
```
.
├─ app.py                              # Local working copy of dashboard app (for deploy via scp)
├─ README.md
├─ DEPLOYMENT.md
├─ etc/
│  ├─ erp_sync.env.example            # Example env file for /etc/erp_sync.env
│  ├─ systemd/system/erp-dashboard.service
│  ├─ nginx/sites-available/erp-dashboard
│  ├─ cron.d/erp_sync
│  └─ logrotate.d/erp-sync
├─ opt/
│  └─ erp/
│     └─ dashboard/requirements.txt   # Flask app dependencies
└─ usr/
   └─ local/bin/erp_env_wrapper       # Cron wrapper to load env and SSM secret
```

### Key Components
- Scripts on instances under `/opt/erp`: `sync_erp.sh`, `encrypt_data.sh`, `decrypt_data.sh`, `backup_to_s3.sh`, `recover_from_backup.sh`, `health_check.sh`, `test_sync.sh`, `demo_scenario.sh`
- Config on instances: `/etc/erp_sync.env` (same passphrase on both nodes)
- Logs: `/var/log/erp_sync*.log`
- Dashboard: Flask+Gunicorn on 8080 behind Nginx 443

### Cron Schedule (on both nodes)
- Every 5 min: bidirectional sync
- Every 2 min: health check
- Daily 02:00: encrypted S3 backup
- Weekly: log rotation + local backup prune

### Common Commands
```bash
# Manual sync
sudo /opt/erp/sync_erp.sh

# Health
sudo /opt/erp/health_check.sh

# Backup now
sudo /opt/erp/backup_to_s3.sh

# Demo
sudo /opt/erp/demo_scenario.sh
```

### Troubleshooting Quick Hits
- SSH blocked: allow your IP in Security Group and `ufw allow from <IP> to any port 22 proto tcp`
- Remote psql prompts: ensure remote block exports `PGPASSWORD` and uses `-h 127.0.0.1`
- Decrypt permission denied: `chmod 755 /opt/erp/decrypt_data.sh`
- Dashboard not loading: `sudo systemctl status erp-dashboard nginx --no-pager`

### Security Notes
- Key-based SSH; restrict 22 to your IP in SG and UFW
- AES‑256‑CBC for data-in-transit files; S3 backups encrypted
- Keep SSM role attached for emergency access

For detailed deployment steps and recovery procedures, see `DEPLOYMENT.md`.

