#!/bin/bash
# Quick print any text as TSPL
echo -e "SIZE 4,6\nCLS\nTEXT 50,50,\"3\",0,1,1,\"$1\"\nPRINT 1" | sudo tee /dev/usb/lp0 > /dev/null
