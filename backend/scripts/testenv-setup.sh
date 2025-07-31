#!/bin/bash

set -e

# Configuration
CONTAINER_NAME="persai-ollama-integration-test"
IMAGE="docker.io/ollama/ollama:latest"
PORT="11434"
VOLUME_NAME="persai_ollama_integration_test_data"
MODEL="llama3.2:3b-instruct-fp16"
TIMEOUT=300

if command -v podman &> /dev/null; then
    DOCKER_CMD="podman"
elif command -v docker &> /dev/null; then
    DOCKER_CMD="docker"
else
    echo "Error: Neither Docker nor Podman is available"
    exit 1
fi

echo "Using $DOCKER_CMD for container management"

is_container_running() {
    $DOCKER_CMD ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" | grep -q "^$CONTAINER_NAME$"
}

container_exists() {
    $DOCKER_CMD ps -a --filter "name=$CONTAINER_NAME" --format "{{.Names}}" | grep -q "^$CONTAINER_NAME$"
}

wait_for_ollama() {
    echo "Waiting for Ollama to be ready..."
    local count=0
    while ! curl -s http://localhost:$PORT/api/tags > /dev/null 2>&1; do
        if [ $count -ge $TIMEOUT ]; then
            echo "Timeout waiting for Ollama service"
            exit 1
        fi
        echo "Waiting for Ollama... ($count/${TIMEOUT}s)"
        sleep 5
        count=$((count + 5))
    done
    echo "✓ Ollama service is ready"
}


start_ollama() {
    echo "Starting Ollama service..."
    
    if ! $DOCKER_CMD volume inspect $VOLUME_NAME > /dev/null 2>&1; then
        echo "Creating volume $VOLUME_NAME..."
        $DOCKER_CMD volume create $VOLUME_NAME
    fi
    
    if container_exists; then
        echo "Removing existing container..."
        $DOCKER_CMD rm -f $CONTAINER_NAME
    fi

    if ! $DOCKER_CMD run -d \
        --name $CONTAINER_NAME \
        -p $PORT:$PORT \
        -e OLLAMA_HOST=0.0.0.0 \
        -v $VOLUME_NAME:/root/.ollama \
        --entrypoint /bin/bash \
        $IMAGE \
        -c "ollama serve"; then
        echo "Error: Failed to start container"
        exit 1
    fi
    
    sleep 2
    if ! is_container_running; then
        echo "Error: Container failed to start or exited immediately"
        echo "Container logs:"
        show_logs
        exit 1
    fi
    
    wait_for_ollama
    
    echo "Pulling model $MODEL (this may take a while)..."
    $DOCKER_CMD exec $CONTAINER_NAME ollama pull $MODEL
    
    echo "✓ Model $MODEL is ready"
    
    echo "✓ Ollama service is ready with model $MODEL"
}

stop_ollama() {
    echo "Stopping Ollama service..."
    if is_container_running; then
        $DOCKER_CMD stop $CONTAINER_NAME
        echo "✓ Ollama service stopped"
    else
        echo "Ollama service is not running"
    fi
}

cleanup() {
    echo "Cleaning up..."
    
    if container_exists; then
        $DOCKER_CMD rm -f $CONTAINER_NAME
        echo "✓ Container removed"
    fi
    
    if $DOCKER_CMD volume inspect $VOLUME_NAME > /dev/null 2>&1; then
        $DOCKER_CMD volume rm $VOLUME_NAME
        echo "✓ Volume removed"
    fi
    
    echo "✓ Cleanup complete"
}

show_logs() {
    if container_exists; then
        $DOCKER_CMD logs $CONTAINER_NAME
    else
        echo "Container $CONTAINER_NAME does not exist"
    fi
}

health_check() {
    echo "Checking service health..."
    if curl -s http://localhost:$PORT/api/tags > /dev/null; then
        echo "✓ Ollama is healthy"
        if curl -s http://localhost:$PORT/api/tags | grep -q "$MODEL"; then
            echo "✓ Model $MODEL is available"
        else
            echo "✗ Model $MODEL is not available"
        fi
    else
        echo "✗ Ollama is not responding"
    fi
}

# Main command handling
case "${1:-}" in
    "start")
        start_ollama
        ;;
    "stop")
        stop_ollama
        ;;
    "clean")
        cleanup
        ;;
    "logs")
        show_logs
        ;;
    "health")
        health_check
        ;;
    "restart")
        stop_ollama
        start_ollama
        ;;
    "help"|"--help"|"-h")
        echo "Usage: $0 {start|stop|clean|logs|health|restart|help}"
        echo ""
        echo "Commands:"
        echo "  start           - Start Ollama service and pull model"
        echo "  stop            - Stop Ollama service"
        echo "  clean           - Stop service and remove containers/volumes"
        echo "  logs            - Show container logs"
        echo "  health          - Check service health"
        echo "  restart         - Stop and start service"
        echo "  help            - Show this help message"
        ;;
    *)
        echo "Usage: $0 {start|stop|clean|logs|health|restart|help}"
        echo "Run '$0 help' for more information"
        exit 1
        ;;
esac
