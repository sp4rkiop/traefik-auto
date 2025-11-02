#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Check if running as root
if [[ $EUID -ne 0 ]]; then
  echo -e "${RED}This script must be run as root${NC}"
  exit 1
fi

URL="https://raw.githubusercontent.com/sp4rkiop/traefik-auto/main/py-scripts/traefik_manager.py"
FILE_NAME="/tmp/traefik_manager.py"

echo "🚀 Traefik Automated Setup"
echo "======================================"
echo "📥 Downloading the python setup script..."

curl -4sSL -o "$FILE_NAME" "$URL"

echo "🔧 Starting interactive setup..."
python3 "$FILE_NAME" "$@"