# Thermal Printer Setup - ATK Fabrication

## Quick Commands

### Print simple text
curl -X POST http://thermal.local:8765/print -d Your text here

### Print shipping label
curl -X POST http://thermal.local:8765/shipping -d ORDER123
