#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if running as root
if [[ $EUID -ne 0 ]]; then
  echo -e "${RED}This script must be run as root${NC}"
  exit 1
fi

URL="https://raw.githubusercontent.com/sp4rkiop/traefik-auto/refs/heads/main/scripts/traefik_manager.py"
FILE_NAME="/tmp/traefik_manager.py"
DEBUG_FILE="/tmp/traefik_download_debug.log"

echo "🚀 Traefik Automated Setup"
echo "======================================"

# Create debug log
echo "Debug log - $(date)" > "$DEBUG_FILE"
echo "URL: $URL" >> "$DEBUG_FILE"
echo "Target file: $FILE_NAME" >> "$DEBUG_FILE"
echo "curl version: $(curl --version | head -1)" >> "$DEBUG_FILE"
echo "Network test:" >> "$DEBUG_FILE"

# Test network connectivity first
if ping -c 1 github.com >> "$DEBUG_FILE" 2>&1; then
  echo "✅ Network connectivity: OK" | tee -a "$DEBUG_FILE"
else
  echo "❌ Network connectivity: FAILED" | tee -a "$DEBUG_FILE"
  echo -e "${RED}Network connectivity test failed. Check your internet connection.${NC}"
  cat "$DEBUG_FILE"
  exit 1
fi

echo "📥 Downloading the python setup script..."

# Try multiple download methods
download_success=false

# Method 1: curl with verbose output
if curl -4sSL -f -v -o "$FILE_NAME" "$URL" >> "$DEBUG_FILE" 2>&1; then
  download_success=true
  echo "✅ Download method 1 (curl) successful"
fi

# Method 2: wget if curl fails
if [ "$download_success" = false ]; then
  echo "⚠️  curl failed, trying wget..." | tee -a "$DEBUG_FILE"
  if wget -q -O "$FILE_NAME" "$URL" >> "$DEBUG_FILE" 2>&1; then
    download_success=true
    echo "✅ Download method 2 (wget) successful"
  fi
fi

# Method 3: python urllib
if [ "$download_success" = false ]; then
  echo "⚠️  wget failed, trying python..." | tee -a "$DEBUG_FILE"
  if python3 -c "
import urllib.request
import sys
try:
    with urllib.request.urlopen('$URL') as response:
        with open('$FILE_NAME', 'wb') as f:
            f.write(response.read())
    print('SUCCESS')
except Exception as e:
    print(f'FAILED: {e}')
    sys.exit(1)
" >> "$DEBUG_FILE" 2>&1; then
    download_success=true
    echo "✅ Download method 3 (python) successful"
  fi
fi

if [ "$download_success" = false ]; then
  echo -e "${RED}❌ All download methods failed${NC}"
  echo -e "${YELLOW}Debug information saved to: $DEBUG_FILE${NC}"
  echo -e "${YELLOW}First few lines of downloaded file:${NC}"
  head -10 "$FILE_NAME" 2>/dev/null || echo "No file content available"
  echo -e "${YELLOW}Debug log:${NC}"
  cat "$DEBUG_FILE"
  exit 1
fi

# Verify the downloaded file
echo "🔍 Verifying downloaded file..."

if [ ! -f "$FILE_NAME" ]; then
  echo -e "${RED}❌ Downloaded file doesn't exist${NC}"
  exit 1
fi

file_size=$(stat -c%s "$FILE_NAME" 2>/dev/null || stat -f%z "$FILE_NAME" 2>/dev/null || echo "0")
if [ "$file_size" -lt 100 ]; then
  echo -e "${RED}❌ Downloaded file is too small ($file_size bytes)${NC}"
  echo -e "${YELLOW}File content:${NC}"
  cat "$FILE_NAME"
  exit 1
fi

# Check for common error indicators
if head -n 5 "$FILE_NAME" | grep -q "404\|Not Found\|Error\|Failed"; then
  echo -e "${RED}❌ Downloaded file appears to contain an error page${NC}"
  echo -e "${YELLOW}File content preview:${NC}"
  head -10 "$FILE_NAME"
  exit 1
fi

# Make the file executable
chmod +x "$FILE_NAME"

echo "✅ Download verification passed ($file_size bytes)"
echo "🔧 Starting interactive setup..."

# Run the Python script
python3 "$FILE_NAME" "$@"

# Clean up debug file on successful completion
rm -f "$DEBUG_FILE"