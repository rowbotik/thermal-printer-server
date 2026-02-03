#!/bin/bash
# TSPL Shipping Label Generator
ORDER="${1:-TEST}"
CUSTOMER="${2:-Customer}"

cat << TSPL | sudo tee /dev/usb/lp0 > /dev/null
SIZE 4,6
DIRECTION 0,0
REFERENCE 0,0
CLS
TEXT 50,30,"3",0,1,1,"ATK FABRICATION CO."
TEXT 50,100,"2",0,1,1,"Order: #$ORDER"
TEXT 50,160,"2",0,1,1,"Date: $(date +%Y-%m-%d)"
TEXT 50,240,"2",0,1,1,"Ship To:"
TEXT 70,300,"2",0,1,1,"$CUSTOMER"
BARCODE 100,420,"128",80,1,0,2,2,"$ORDER"
TEXT 100,520,"1",0,1,1,"$ORDER"
PRINT 1,1
TSPL
echo "Label printed: Order #$ORDER for $CUSTOMER"
