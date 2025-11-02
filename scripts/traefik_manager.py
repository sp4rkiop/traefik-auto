#!/usr/bin/env python3

import os
import sys
import subprocess
import time
from pathlib import Path

# Global configuration constants
TRAEFIK_BASE_PATH = "/opt/traefik"
TRAEFIK_CONFIG_PATH = "/etc/traefik"
TRAEFIK_CERTS_PATH = "/etc/traefik/certs"
TEST_COMPOSE_PATH = "/tmp/traefik_test_page"
TEST_SCRIPT_PATH = "/tmp/remove_test_page.sh"

# Colors for output
class Colors:
    RED: str = '\033[0;31m'
    GREEN: str = '\033[0;32m'
    YELLOW: str = '\033[1;33m'
    BLUE: str = '\033[0;34m'
    NC: str = '\033[0m'

def print_message(state: str, message: str) -> None:
    """Print message with colored formatting based on state"""
    color_map = {
        "status": Colors.BLUE,
        "success": Colors.GREEN,
        "warning": Colors.YELLOW,
        "error": Colors.RED
    }
    
    prefix_map = {
        "status": "[INFO]",
        "success": "[SUCCESS]",
        "warning": "[WARNING]",
        "error": "[ERROR]"
    }
    
    color = color_map.get(state, Colors.BLUE)
    prefix = prefix_map.get(state, "[INFO]")
    
    print(f"{color}{prefix}{Colors.NC} {message}")

def run_command(cmd: str | list[str], shell: bool = False) -> bool:
    """Run a command and return success status"""
    try:
        if shell:
            _ = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        else:
            if isinstance(cmd, str):
                cmd = cmd.split()
            _ = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print_message("error", f"Command failed: {e}")
        return False
    except Exception as e:
        print_message("error", f"Unexpected error: {e}")
        return False

def check_docker() -> None:
    """Check if Docker is installed and running"""
    print_message("status", "Checking Docker installation...")
    if not run_command(["docker", "--version"]):
        print_message("error", "Docker is not installed. Please install Docker first.")
        sys.exit(1)
    
    if not run_command(["docker", "info"]):
        print_message("error", "Docker daemon is not running. Please start Docker first.")
        sys.exit(1)
    
    print_message("success", "Docker is installed and running")

def get_user_input() -> tuple[str | None, str | None]:
    """Get user input interactively"""
    print_message("status", "Traefik Setup Configuration")
    print("==================================")
    
    email = input("Enter your email for Let's Encrypt (optional): ").strip()
    if not email:
        email = None
    test_domain = input("Enter test domain/subdomain (optional, e.g., test.yourdomain.com): ").strip()
    if not test_domain:
        test_domain = None
    
    if test_domain:
        confirm = input("Test page will auto-remove after 10 minutes. Continue? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print_message("status", "Setup cancelled.")
            sys.exit(0)
    
    return email, test_domain

def check_dns_resolution(domain: str) -> None:
    """Check if domain resolves to this server"""
    print_message("status", f"Checking DNS resolution for {domain}...")
    
    try:
        # Get server's public IP using external service
        result = subprocess.run(["curl", "-4s", "https://api.ipify.org"],
                              capture_output=True, text=True)
        if result.returncode == 0:
            server_ip = result.stdout.strip()
            print_message("warning", f"⚠️  Make sure {domain} DNS A record points to: {server_ip}")
            print_message("warning", "If DNS is not configured, the test page won't be accessible")
            
            # Quick DNS check
            dns_check = subprocess.run(["nslookup", domain], capture_output=True, text=True)
            if dns_check.returncode != 0:
                print_message("warning", f"❌ DNS lookup failed for {domain}")
            else:
                print_message("success", f"✅ DNS lookup successful for {domain}")
                
    except Exception as e:
        print_message("warning", f"Could not determine server IP. Please ensure {domain} points to your server. Error: {e}")

def create_directories() -> None:
    """Create necessary directories"""
    directories = [
        TRAEFIK_BASE_PATH,
        TRAEFIK_CONFIG_PATH,
        TRAEFIK_CERTS_PATH
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print_message("success", "Directories created")

def create_traefik_config(email: str | None) -> None:
    """Create Traefik configuration file"""
    config_content = f"""# Traefik Global Configuration
global:
  checkNewVersion: false
  sendAnonymousUsage: false
api:
  dashboard: true
  insecure: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false

certificatesResolvers:
  letsencrypt:
    acme:
      email: {email or "admin@example.com"}
      storage: {TRAEFIK_CERTS_PATH}/acme.json
      httpChallenge:
        entryPoint: web
"""
    
    with open(f"{TRAEFIK_CONFIG_PATH}/traefik.yml", "w") as f:
        _ = f.write(config_content)
    
    print_message("success", "Traefik configuration created")

def create_traefik_compose() -> None:
    """Create Docker Compose file for Traefik"""
    compose_content = """version: '3.8'

services:
  traefik:
    image: traefik:v3.4
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    networks:
      - traefik
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - {TRAEFIK_CONFIG_PATH}/traefik.yml:/etc/traefik/traefik.yml:ro
      - {TRAEFIK_CERTS_PATH}:/etc/traefik/certs

networks:
  traefik:
    external: true
    name: traefik
"""
    
    with open(f"{TRAEFIK_BASE_PATH}/docker-compose.yml", "w") as f:
        _ = f.write(compose_content)
    
    print_message("success", "Docker Compose configuration created")

def create_test_compose(test_domain: str | None) -> None:
    """Create test page Docker Compose file using Nginx with a custom page"""
    if not test_domain:
        return
    
    # Use the global test compose path
    Path(TEST_COMPOSE_PATH).mkdir(parents=True, exist_ok=True)
    
    # Create index.html with proper escaping
    index_content = f"<h1>Traefik + Nginx Test Page</h1><p>Domain: {test_domain}</p>"
    with open(f"{TEST_COMPOSE_PATH}/index.html", "w", encoding="utf-8") as f:
        _ = f.write(index_content)
    
    # Create docker-compose.yml with proper escaping
    compose_content = f"""version: '3.8'

services:
  nginx-test:
    image: nginx:latest
    container_name: nginx-test
    restart: no
    networks:
      - traefik
    volumes:
      - {Path(TEST_COMPOSE_PATH).resolve()}:/usr/share/nginx/html:ro
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.nginx-test.rule=Host(`{test_domain}`)"
      - "traefik.http.routers.nginx-test.entrypoints=websecure"
      - "traefik.http.routers.nginx-test.tls.certresolver=letsencrypt"

networks:
  traefik:
    external: true
    name: traefik
"""
    
    with open(f"{TEST_COMPOSE_PATH}/docker-compose-test.yml", "w", encoding="utf-8") as f:
        _ = f.write(compose_content)
    
    print_message("success", "Nginx test service configuration created with custom HTML page")


def setup_docker_network() -> None:
    """Create Docker network if it doesn't exist"""
    print_message("status", "Setting up Docker network...")
    
    result = subprocess.run(["docker", "network", "ls", "--format", "{{.Name}}"],
                          capture_output=True, text=True)
    
    if "traefik" not in result.stdout:
        if run_command(["docker", "network", "create", "traefik"]):
            print_message("success", "Docker network 'traefik' created")
    else:
        print_message("warning", "Docker network 'traefik' already exists")

def deploy_traefik() -> None:
    """Deploy Traefik"""
    print_message("status", "Deploying Traefik...")
    
    try:
        os.chdir(TRAEFIK_BASE_PATH)
    except OSError as e:
        print_message("error", f"Failed to change to {TRAEFIK_BASE_PATH} directory: {e}")
    
    # Start services with proper argument handling
    compose_cmd = ["docker", "compose", "-f", f"{TRAEFIK_BASE_PATH}/docker-compose.yml", "up", "-d"]
    if run_command(compose_cmd):
        print_message("success", "Traefik deployed successfully")
    else:
        print_message("error", "Failed to deploy Traefik")

def deploy_test_page(test_domain: str | None) -> None:
    """Deploy test page and schedule auto-removal"""
    if not test_domain:
        return
    
    print_message("status", "Deploying test page (will auto-remove in 10 minutes)...")
    
    # Use proper argument handling to avoid shell injection
    compose_cmd = ["docker", "compose", "-f", f"{TEST_COMPOSE_PATH}/docker-compose-test.yml", "up", "-d"]
    
    if run_command(compose_cmd):
        print_message("success", f"Test page deployed at https://{test_domain}")
        
        # Schedule auto-removal
        import shlex
        _ = shlex.quote(test_domain)
        safe_path = shlex.quote(TEST_COMPOSE_PATH)
        safe_script = shlex.quote(TEST_SCRIPT_PATH)
        
        removal_script = f"""#!/bin/bash
sleep 600
echo ""
echo "⏰ Time is up! Removing test page..."
docker compose -f {safe_path}/docker-compose-test.yml down
rm -rf {safe_path}
rm -f {safe_script}
echo "✅ Test page removed successfully"
"""
        
        with open(TEST_SCRIPT_PATH, "w") as f:
            _ = f.write(removal_script)
        
        _ = run_command(f"chmod +x {TEST_SCRIPT_PATH}", shell=True)
        _ = run_command(f"nohup {TEST_SCRIPT_PATH} > /dev/null 2>&1 &", shell=True)
        
        removal_time = time.strftime("%H:%M:%S", time.localtime(time.time() + 600))
        print_message("warning", f"Test page will auto-remove in 10 minutes (at {removal_time})")

def display_final_info(test_domain: str | None) -> None:
    """Display final setup information"""
    print_message("success", "Traefik setup completed!")
    print("")
    print("Summary:")
    print("--------")
    print(f"• Traefik configuration: {TRAEFIK_CONFIG_PATH}/")
    print(f"• Docker Compose files: {TRAEFIK_BASE_PATH}/")
    print("• Docker network: traefik")
    print("")
    
    if test_domain:
        print("🎉 Your test page is available at:")
        print(f"  • https://{test_domain}")
        print("")
        print("⏰ Test page will auto-remove in 10 minutes")
    else:
        print("No test domain provided - only Traefik is running.")
        print("You can add services by:")
        print("1. Adding them to the 'traefik' network")
        print("2. Setting appropriate Traefik labels")
    
    print("")
    print("To manage Traefik:")
    print(f"  cd {TRAEFIK_BASE_PATH} && docker compose [logs|restart|down]")
    print("")
    
    if test_domain:
        print("To manually remove test page early:")
        print(f"  docker compose -f {TEST_COMPOSE_PATH}/docker-compose-test.yml down")

def main() -> None:
    """Main setup function"""
    print_message("status", "Starting Traefik automated setup...")
    
    # Check prerequisites
    check_docker()
    
    # Get user input
    email, test_domain = get_user_input()
    
    # Check DNS if domain provided
    if test_domain:
        check_dns_resolution(test_domain)
    
    # Setup
    create_directories()
    create_traefik_config(email)
    create_traefik_compose()
    create_test_compose(test_domain)
    setup_docker_network()
    
    # Deploy
    deploy_traefik()
    deploy_test_page(test_domain)
    
    # Final info
    display_final_info(test_domain)
    print_message("success", "Setup complete! 🎉")

if __name__ == "__main__":
    main()