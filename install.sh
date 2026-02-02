#!/bin/bash
#
# Install script for Thermal Printer Server
# Sets up ORGSTA T001 printer with HTTP API
#

set -e

INSTALL_DIR="/opt/thermal-printer"
SERVICE_NAME="thermal-printer"
USER="pi"

echo "==================================="
echo "Thermal Printer Server Installer"
echo "==================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

# Update system
echo "[1/7] Updating package list..."
apt-get update

# Install dependencies
echo "[2/7] Installing dependencies..."
apt-get install -y python3 python3-pip python3-pil libopenjp2-7 libtiff5

# Create install directory
echo "[3/7] Creating install directory..."
mkdir -p $INSTALL_DIR
cp print_server.py $INSTALL_DIR/
chown -R $USER:$USER $INSTALL_DIR

# Add user to lp group for printer access
echo "[4/7] Setting up printer permissions..."
usermod -a -G lp $USER

# Create systemd service
echo "[5/7] Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Thermal Printer HTTP Server
After=network.target

[Service]
Type=simple
User=$USER
Group=lp
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/print_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "[6/7] Enabling service..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME

echo "[7/7] Starting service..."
systemctl start $SERVICE_NAME

echo ""
echo "==================================="
echo "Installation Complete!"
echo "==================================="
echo ""
echo "Service status:"
systemctl status $SERVICE_NAME --no-pager

echo ""
echo "Test the printer:"
echo "  curl http://localhost:8765/"
echo ""
echo "If printer is not at /dev/usb/lp0, update the device path in:"
echo "  $INSTALL_DIR/print_server.py"
