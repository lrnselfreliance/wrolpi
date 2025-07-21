#!/bin/bash
set -e

# List of images to push
IMAGES=(
  "lrnselfreliance/wrolpi:wrolpi-api-latest"
  "lrnselfreliance/wrolpi:wrolpi-archive-latest"
  "lrnselfreliance/wrolpi:wrolpi-app-latest"
  "lrnselfreliance/wrolpi:wrolpi-web-latest"
  "lrnselfreliance/wrolpi:wrolpi-zim-latest"
  "lrnselfreliance/wrolpi:wrolpi-help-latest"
  "lrnselfreliance/wrolpi:wrolpi-map-latest"
  "lrnselfreliance/wrolpi:wrolpi-map_https-latest"
  "lrnselfreliance/wrolpi:wrolpi-zim_https-latest"
  "lrnselfreliance/wrolpi:wrolpi-help_https-latest"
)

# Check if Docker Hub credentials are available
if ! docker system info --format '{{.IndexServerAddress}}' 2>/dev/null | grep -q "docker.io"; then
  echo "Error: Not logged in to Docker Hub or credentials not accessible."
  echo "Attempting to log in to Docker Hub..."
  docker login -u lrnselfreliance
  if [ $? -ne 0 ]; then
    echo "Error: Docker login failed. Please run 'docker login -u lrnselfreliance' manually and enter your password."
    exit 1
  fi
  echo "Docker login successful."
fi

# Push each image
for image in "${IMAGES[@]}"; do
  echo "Pushing $image..."
  docker push "$image" || {
    echo "Error: Failed to push $image"
    exit 1
  }
done

echo "All images pushed successfully!"