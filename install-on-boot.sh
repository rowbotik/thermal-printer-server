#!/bin/bash
#
# Auto-update script for Thermal Printer Server
# Run on boot to pull latest version from GitHub
#

REPO_URL="https://github.com/rowbotik/thermal-printer-server.git"
INSTALL_DIR="/opt/thermal-printer"
SERVICE_NAME="thermal-printer"
LOG_FILE="/var/log/thermal-printer-boot.log"

echo "$(date): Starting thermal-printer boot update..." >> $LOG_FILE

# Check if we're online
if ! ping -c 1 github.com > /dev/null 2>&1; then
    echo "$(date): No internet connection, skipping update" >> $LOG_FILE
    exit 0
fi

# Create temp directory
TEMP_DIR=$(mktemp -d)
cd $TEMP_DIR

# Clone latest
echo "$(date): Pulling latest from GitHub..." >> $LOG_FILE
if git clone --depth 1 $REPO_URL . >> $LOG_FILE 2>&1; then
    # Check if print_server.py changed
    if ! diff -q print_server.py $INSTALL_DIR/print_server.py > /dev/null 2>&1; then
        echo "$(date): New version found, updating..." >> $LOG_FILE
        
        # Stop service
        systemctl stop $SERVICE_NAME >> $LOG_FILE 2>&1
        
        # Update files
        cp print_server.py $INSTALL_DIR/
        chown -R pi:pi $INSTALL_DIR
        
        # Restart service
        systemctl start $SERVICE_NAME >> $LOG_FILE 2>&1
        
        echo "$(date): Update complete" >> $LOG_FILE
    else
        echo "$(date): Already up to date" >> $LOG_FILE
    fi
else
    echo "$(date): Failed to clone repository" >> $LOG_FILE
fi

# Cleanup
cd /
rm -rf $TEMP_DIR

echo "$(date): Boot update finished" >> $LOG_FILE
