#!/bin/bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

check_podman_installation() {
    log "Checking Podman installation..."
    
    if ! command -v podman &> /dev/null; then
        error "Podman is not installed. Please install it first:"
        echo "  brew install podman"
        exit 1
    fi
    
    log "Podman found: $(podman --version)"
}

check_podman_machine() {
    log "Checking Podman machine status..."
    
    # Check if any machine exists
    if ! podman machine list --format json | jq -e '. | length > 0' &> /dev/null; then
        log "No Podman machine found. Creating default machine..."
        podman machine init --cpus 8 --memory 65536 --disk-size 50
    fi
    
    # Check if machine is running
    local machine_status=$(podman machine list --format json | jq -r '.[0].Running' 2>/dev/null || echo "false")
    
    if [[ "$machine_status" != "true" ]]; then
        log "Starting Podman machine..."
        podman machine start
        
        # Wait for machine to be ready
        log "Waiting for Podman machine to be ready..."
        local attempts=0
        while ! podman info &> /dev/null && [[ $attempts -lt 30 ]]; do
            sleep 2
            attempts=$((attempts + 1))
        done
        
        if [[ $attempts -ge 30 ]]; then
            error "Podman machine failed to start within 60 seconds"
            exit 1
        fi
    else
        log "Podman machine is already running"
    fi
}

configure_docker_compatibility() {
    log "Configuring Docker compatibility..."
    
    # Create docker socket symlink if it doesn't exist
    local docker_sock="/var/run/docker.sock"
    local podman_sock=$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null | head -1)
    
    if [[ -n "$podman_sock" ]]; then
        debug "Podman socket: $podman_sock"
        
        # Export DOCKER_HOST for current session
        export DOCKER_HOST="unix://$podman_sock"
        echo "export DOCKER_HOST=\"unix://$podman_sock\"" > /tmp/podman-env
        log "Set DOCKER_HOST=$DOCKER_HOST"
        
        # Create alias for docker command
        if ! grep -q "alias docker=podman" ~/.zshrc 2>/dev/null; then
            echo "alias docker=podman" >> ~/.zshrc
            log "Added docker=podman alias to ~/.zshrc"
        fi
    else
        warn "Could not determine Podman socket path"
    fi
}

test_podman_connection() {
    log "Testing Podman connection..."
    
    if podman info &> /dev/null; then
        log "✅ Podman is working correctly"
        podman version --format "{{.Client.Version}}"
    else
        error "❌ Podman connection test failed"
        exit 1
    fi
}

configure_act_for_podman() {
    log "Configuring Act for Podman..."
    
    # Update .actrc to use linux/amd64 architecture for M-series Macs
    local actrc_file="$(dirname "$0")/../.actrc"
    
    if [[ ! -f "$actrc_file" ]]; then
        warn ".actrc not found, creating it..."
        touch "$actrc_file"
    fi
    
    # Add container architecture for Apple Silicon
    if ! grep -q "container-architecture" "$actrc_file"; then
        echo "--container-architecture linux/amd64" >> "$actrc_file"
        log "Added container architecture to .actrc"
    fi
    
    # Ensure we use the right socket
    local podman_sock=$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null | head -1)
    if [[ -n "$podman_sock" ]]; then
        if ! grep -q "DOCKER_HOST" "$actrc_file"; then
            echo "--env DOCKER_HOST=unix://$podman_sock" >> "$actrc_file"
            log "Added DOCKER_HOST to .actrc"
        fi
    fi
}

show_usage_instructions() {
    log "🎉 Podman setup complete!"
    echo
    echo "To use Podman with Act, run:"
    echo "  source /tmp/podman-env  # Set DOCKER_HOST for current session"
    echo "  act --list              # Test Act with Podman"
    echo
    echo "For permanent setup, add to your shell profile:"
    echo "  export DOCKER_HOST=\"unix://$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null | head -1)\""
    echo
    echo "Or use the alias:"
    echo "  docker ps               # Will use podman"
}

main() {
    log "Setting up Podman for Act (Docker alternative)..."
    
    check_podman_installation
    check_podman_machine
    configure_docker_compatibility
    test_podman_connection
    configure_act_for_podman
    show_usage_instructions
}

# Execute main function
main "$@"