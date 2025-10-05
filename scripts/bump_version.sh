#!/bin/bash

# Version bumping script for MQTT Interceptor
# This script updates the version in both Python code and docker-compose.yml
# to ensure Docker cache is busted on each release

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 1.2.1"
    exit 1
fi

NEW_VERSION=$1

echo "Updating version to $NEW_VERSION..."

# Update VERSION in Python code
sed -i.bak "s/VERSION = '[^']*'/VERSION = '$NEW_VERSION'/" mqtt_interceptor.py

# Update BUILD_VERSION in docker-compose.yml
sed -i.bak "s/BUILD_VERSION=[0-9.]*/BUILD_VERSION=$NEW_VERSION/" docker-compose.yml

# Clean up backup files
rm -f mqtt_interceptor.py.bak docker-compose.yml.bak

echo "Version updated to $NEW_VERSION in:"
echo "  - mqtt_interceptor.py"
echo "  - docker-compose.yml"
echo ""
echo "This will force Docker to rebuild without cache on next deployment."
echo "Commit and push these changes to update your deployment."
