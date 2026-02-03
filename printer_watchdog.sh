#!/bin/bash
# Keep printer connected
while true; do
    if [ ! -e /dev/usb/lp0 ]; then
        echo Sun Feb 1 13:32:12 EST 2026: Printer disconnected, reloading driver...
        sudo modprobe -r usblp 2>/dev/null
        sudo modprobe usblp 2>/dev/null
    fi
    sleep 10
done
