#!/bin/bash
# setup.sh - Post-flash setup for Raspberry Pi Zero W running Bookworm
#
# Run this script after flashing Bookworm and SSHing into the Pi:
#   curl -fsSL https://raw.githubusercontent.com/brianegge/6160-st-device/master/setup.sh | bash
# Or clone the repo first and run locally:
#   git clone https://github.com/brianegge/6160-st-device.git
#   cd 6160-st-device && bash setup.sh

set -euo pipefail

REPO_URL="https://github.com/brianegge/6160-st-device.git"
REPO_DIR="$HOME/6160-st-device"
NAS_HOST="ubuntu@nas.home"
NAS_BACKUP_BASE="/mnt/elements2/backups"
NAS_BACKUP_DIR="$NAS_BACKUP_BASE/$(hostname)"

echo "=== Step 1: Add pi user to dialout group ==="
sudo usermod -aG dialout pi

echo "=== Step 2: Install system packages ==="
sudo apt update
sudo apt install -y podman git snmpd

echo "=== Step 3: Clone repository ==="
if [ -d "$REPO_DIR" ]; then
    echo "Repository already exists at $REPO_DIR, pulling latest..."
    cd "$REPO_DIR"
    git pull
else
    git clone "$REPO_URL" "$REPO_DIR"
    cd "$REPO_DIR"
fi

echo "=== Step 4: Configure git hooks ==="
cd "$REPO_DIR"
git config core.hooksPath .githooks

echo "=== Step 5: Install podman quadlet ==="
mkdir -p ~/.config/containers/systemd
cp "$REPO_DIR/quadlet/keypad6160.container" ~/.config/containers/systemd/
cp "$REPO_DIR/quadlet/keypad6160.env" ~/.config/containers/systemd/

# Enable podman socket for auto-update timer
systemctl --user enable --now podman-auto-update.timer

# Reload systemd to pick up the quadlet
systemctl --user daemon-reload
systemctl --user enable keypad6160
echo "Service enabled. Start it with: systemctl --user start keypad6160"
echo "(Not starting automatically — verify env config first)"

# Enable lingering so user services start at boot without login
sudo loginctl enable-linger pi

echo "=== Step 6: Configure SNMP ==="
sudo cp "$REPO_DIR/snmpd.conf" /etc/snmp/snmpd.conf
sudo systemctl enable --now snmpd
echo "Verifying SNMP..."
sleep 2
snmpwalk -v2c -c egge localhost system || echo "SNMP verification failed — check snmpd status"

echo "=== Step 7: Set up backup to NAS ==="
echo "Generating SSH key (press Enter for defaults)..."
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
    ssh-keygen -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519"
    echo "Copy this key to the NAS:"
    echo "  ssh-copy-id $NAS_HOST"
    echo "Then create the backup directory:"
    echo "  ssh $NAS_HOST mkdir -p $NAS_BACKUP_DIR"
else
    echo "SSH key already exists, skipping generation"
fi

# Install cron job for weekly home directory rsync (runs as pi)
CRON_CMD="@weekly rsync -avz --exclude='node_modules' /home/pi $NAS_HOST:$NAS_BACKUP_DIR/"
(crontab -l 2>/dev/null | grep -v "$NAS_BACKUP_DIR" || true; echo "$CRON_CMD") | crontab -
echo "Weekly home directory backup cron job installed (as pi)"

echo "=== Step 8: Install SD card backup scripts ==="
# Install sd-backup.sh to ~/bin/
mkdir -p "$HOME/bin"
cp "$REPO_DIR/bin/sd-backup.sh" "$HOME/bin/sd-backup.sh"
chmod +x "$HOME/bin/sd-backup.sh"
echo "Installed sd-backup.sh to ~/bin/"

# Deploy nas-rotate-and-shrink.sh to NAS
echo "Deploying nas-rotate-and-shrink.sh to NAS..."
scp -i "$HOME/.ssh/id_ed25519" "$REPO_DIR/bin/nas-rotate-and-shrink.sh" \
    "$NAS_HOST:$NAS_BACKUP_BASE/nas-rotate-and-shrink.sh"
ssh -i "$HOME/.ssh/id_ed25519" "$NAS_HOST" "chmod +x $NAS_BACKUP_BASE/nas-rotate-and-shrink.sh"
echo "Deployed nas-rotate-and-shrink.sh to NAS"

# Install root cron job for weekly SD card backup
SD_CRON_CMD="@weekly /home/pi/bin/sd-backup.sh >> /var/log/sd-backup.log 2>&1"
(sudo crontab -l 2>/dev/null | grep -v "sd-backup" || true; echo "$SD_CRON_CMD") | sudo crontab -
echo "Weekly SD card backup cron job installed (as root)"

# Ensure root can SSH to NAS using pi's key
echo "Adding NAS to root's known_hosts..."
sudo mkdir -p /root/.ssh
sudo ssh-keyscan -H nas.home 2>/dev/null | sudo tee -a /root/.ssh/known_hosts >/dev/null
echo "NOTE: Root SSH to NAS uses pi's key (-i /home/pi/.ssh/id_ed25519)."
echo "Ensure the NAS authorized_keys accepts this key for user 'ubuntu'."

echo ""
echo "=== Setup complete ==="
echo ""
echo "Remaining manual steps:"
echo "  1. Copy SSH key to NAS:  ssh-copy-id $NAS_HOST"
echo "  2. Create NAS backup dir: ssh $NAS_HOST mkdir -p $NAS_BACKUP_DIR"
echo "  3. Verify MQTT config in: ~/.config/containers/systemd/keypad6160.env"
echo "  4. Start the service:     systemctl --user start keypad6160"
echo "  5. Check service status:  systemctl --user status keypad6160"
echo "  6. Check logs:            journalctl --user -u keypad6160 -n 20"
echo "  7. Verify SNMP:           snmpwalk -v2c -c egge localhost system"
echo "  8. Test SD backup:        sudo /home/pi/bin/sd-backup.sh"
echo "  9. Verify root cron:      sudo crontab -l"
