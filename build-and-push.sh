#!/bin/bash
# Build and push Docker image to registry
#
# Usage:
#   ./build-and-push.sh [REGISTRY] [REPOSITORY] [TAG]
#
# Examples:
#   # Docker Hub
#   ./build-and-push.sh docker.io username/finance-agent latest
#   ./build-and-push.sh docker.io username/finance-agent 0.1.0
#
#   # GitHub Container Registry
#   ./build-and-push.sh ghcr.io username/finance-agent latest
#
#   # Default (Docker Hub with latest tag)
#   ./build-and-push.sh

set -e

# Default values
REGISTRY="${1:-docker.io}"
REPOSITORY="${2:-finance-agent}"
TAG="${3:-latest}"

# Construct full image name
if [[ "$REGISTRY" == "docker.io" ]]; then
    # Docker Hub format: docker.io/username/repo:tag
    # If repository doesn't contain '/', assume it's just the repo name
    # User should provide username/repo format for Docker Hub
    IMAGE_NAME="${REGISTRY}/${REPOSITORY}:${TAG}"
else
    # Other registries: registry.io/repo:tag
    IMAGE_NAME="${REGISTRY}/${REPOSITORY}:${TAG}"
fi

echo "Building Docker image: ${IMAGE_NAME}"
docker build -f Dockerfile.finance-agent -t "${IMAGE_NAME}" .

echo "Pushing Docker image to registry..."
docker push "${IMAGE_NAME}"

echo "✅ Successfully pushed ${IMAGE_NAME}"
echo ""
echo "Image URL: ${IMAGE_NAME}"
echo ""
echo "To use this image, update docker-compose.yml:"
echo "  image: ${IMAGE_NAME}"


