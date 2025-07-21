#!/bin/bash
set -e

# Determine build mode from argument
BUILD_MODE="parallel"
if [ "$1" == "--series" ]; then
  BUILD_MODE="series"
elif [ "$1" != "" ] && [ "$1" != "--parallel" ]; then
  echo "Usage: $0 [--parallel | --series]"
  echo "  --parallel: Build images in parallel (default)"
  echo "  --series: Build images in series"
  exit 1
fi

# Determine project root (parent of docker/ if in docker/, or current dir if in project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" == */docker ]]; then
  PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
else
  PROJECT_ROOT="$SCRIPT_DIR"
fi
DOCKER_DIR="$PROJECT_ROOT/docker"

# Verify docker directory exists
if [ ! -d "$DOCKER_DIR" ]; then
  echo "Error: docker/ directory not found in $PROJECT_ROOT"
  exit 1
fi

# Function to build a Docker image
build_image() {
  local tag=$1
  local dockerfile=$2
  echo "Building $tag..."
  docker build -t "$tag" -f "$dockerfile" "$PROJECT_ROOT"
}

# List of images and their Dockerfiles
IMAGES=(
  "lrnselfreliance/wrolpi:wrolpi-api-latest $DOCKER_DIR/api/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-archive-latest $DOCKER_DIR/archive/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-app-latest $DOCKER_DIR/app/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-web-latest $DOCKER_DIR/web/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-zim-latest $DOCKER_DIR/zim/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-help-latest $DOCKER_DIR/help/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-map_https-latest $DOCKER_DIR/https_proxy/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-zim_https-latest $DOCKER_DIR/https_proxy/Dockerfile"
  "lrnselfreliance/wrolpi:wrolpi-help_https-latest $DOCKER_DIR/https_proxy/Dockerfile"
)

# Build images based on mode
if [ "$BUILD_MODE" == "parallel" ]; then
  for image in "${IMAGES[@]}"; do
    read -r tag dockerfile <<< "$image"
    build_image "$tag" "$dockerfile" &
  done
  wait
else
  for image in "${IMAGES[@]}"; do
    read -r tag dockerfile <<< "$image"
    build_image "$tag" "$dockerfile"
  done
fi

echo "All images built successfully!"