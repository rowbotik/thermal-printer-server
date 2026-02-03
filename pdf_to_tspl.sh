#!/bin/bash
# Simple text extraction and TSPL conversion
# Usage: pdf_to_tspl.sh <input.txt or stdin>

INPUT=${1:-/dev/stdin}
TEXT=$(cat "$INPUT" | head -10 | tr '\n' ' ' | cut -c1-200)

echo "SIZE 4,6"
echo "CLS"
echo "TEXT 50,50,\"2\",0,1,1,\"$TEXT\""
echo "PRINT 1"
