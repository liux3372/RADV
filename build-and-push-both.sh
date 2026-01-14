#!/bin/bash
# Build and push both Docker images (finance-agent and finance-evaluator) to registry
#
# Usage:
#   ./build-and-push-both.sh [REGISTRY] [REPOSITORY_PREFIX] [TAG]
#
# Examples:
#   # Docker Hub
#   ./build-and-push-both.sh docker.io username/finance latest
#   ./build-and-push-both.sh docker.io username/finance 0.1.0
#
#   # GitHub Container Registry
#   ./build-and-push-both.sh ghcr.io username/finance latest
#
#   # Default (Docker Hub with latest tag)
#   ./build-and-push-both.sh

set -e

# Default values
REGISTRY="${1:-docker.io}"
REPOSITORY_PREFIX="${2:-finance}"
TAG="${3:-latest}"

# Construct full image names
if [[ "$REGISTRY" == "docker.io" ]]; then
    # Docker Hub format: docker.io/username/repo:tag
    AGENT_IMAGE="${REGISTRY}/${REPOSITORY_PREFIX}-agent:${TAG}"
    EVALUATOR_IMAGE="${REGISTRY}/${REPOSITORY_PREFIX}-evaluator:${TAG}"
else
    # Other registries: registry.io/repo:tag
    AGENT_IMAGE="${REGISTRY}/${REPOSITORY_PREFIX}-agent:${TAG}"
    EVALUATOR_IMAGE="${REGISTRY}/${REPOSITORY_PREFIX}-evaluator:${TAG}"
fi

echo "=========================================="
echo "Building and pushing Finance Agent image"
echo "=========================================="
echo "Building: ${AGENT_IMAGE}"
docker build -f Dockerfile.finance-agent -t "${AGENT_IMAGE}" .

echo "Pushing Finance Agent image..."
docker push "${AGENT_IMAGE}"

echo "✅ Successfully pushed ${AGENT_IMAGE}"
echo ""

echo "=========================================="
echo "Building and pushing Finance Evaluator image"
echo "=========================================="
echo "Building: ${EVALUATOR_IMAGE}"
# Build evaluator image using its own Dockerfile
docker build -f Dockerfile.finance-evaluator -t "${EVALUATOR_IMAGE}" .

echo "Pushing Finance Evaluator image..."
docker push "${EVALUATOR_IMAGE}"

echo "✅ Successfully pushed ${EVALUATOR_IMAGE}"
echo ""

echo "=========================================="
echo "✅ Both images successfully pushed!"
echo "=========================================="
echo ""
echo "Finance Agent image: ${AGENT_IMAGE}"
echo "Finance Evaluator image: ${EVALUATOR_IMAGE}"
echo ""
echo "To use these images, update docker-compose.yml:"
echo "  finance-agent:"
echo "    image: ${AGENT_IMAGE}"
echo "  finance-evaluator:"
echo "    image: ${EVALUATOR_IMAGE}"

