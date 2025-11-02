#!/usr/bin/env python3

import sys
import subprocess
import time
from pathlib import Path

# Global configuration constants
TRAEFIK_BASE_PATH = "/opt/traefik"
TRAEFIK_CERTS_PATH = f"{TRAEFIK_BASE_PATH}/certs"
TRAEFIK_DYNAMIC_PATH = f"{TRAEFIK_BASE_PATH}/dynamic"
HTPASSWD_FILE = f"{TRAEFIK_BASE_PATH}/.htpasswd"
COMPOSE_FILE = f"{TRAEFIK_BASE_PATH}/docker-compose.yml"
TLS_FILE = f"{TRAEFIK_DYNAMIC_PATH}/tls.yaml"
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

def ensure_dirs():
    for d in [TRAEFIK_BASE_PATH, TRAEFIK_CERTS_PATH, TRAEFIK_DYNAMIC_PATH]:
        Path(d).mkdir(parents=True, exist_ok=True)
    print_message("ok", "Created Traefik directories")

def create_self_signed_cert(domain: str):
    print_message("info", "Generating self-signed certificate for *.docker.localhost ...")
    _ = run_command(f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout {TRAEFIK_CERTS_PATH}/local.key \
        -out {TRAEFIK_CERTS_PATH}/local.crt \
        -subj '/CN=*.{domain}'", shell=True)
    print_message("ok", "Self-signed certificate created")

def create_htpasswd():
    print_message("info", "Creating Basic Auth credentials for Traefik Dashboard...")
    user = input("Enter dashboard username [admin]: ").strip() or "admin"
    password = input("Enter dashboard password [P@ssw0rd]: ").strip() or "P@ssw0rd"
    if not run_command("which htpasswd", shell=True):
        print_message("err", "htpasswd not found! Install apache2-utils first.")
        sys.exit(1)
    result = subprocess.run(
        f"htpasswd -nb {user} '{password}' | sed -e 's/\\$/$$/g'",
        shell=True, capture_output=True, text=True
    )
    with open(HTPASSWD_FILE, "w") as f:
        _ = f.write(result.stdout.strip())
    print_message("ok", f"Dashboard credentials created and stored in {HTPASSWD_FILE}")

def create_dynamic_tls():
    content = """tls:
  certificates:
    - certFile: /certs/local.crt
      keyFile:  /certs/local.key
"""
    _ = Path(TLS_FILE).write_text(content)
    print_message("ok", f"Dynamic TLS config written to {TLS_FILE}")

def ask_for_resolver():
    print("\nSSL Resolver Options:")
    print("1. Self-signed (local HTTPS)")
    print("2. Let's Encrypt (HTTP Challenge)")
    print("3. Cloudflare DNS Challenge")
    choice = input("Select resolver [1/2/3]: ").strip()
    email = "admin@docker.localhost"
    domain = "docker.localhost"
    cloudflare_email = None
    cloudflare_api_token = None
    if choice in ["2", "3"]:
        domain = input("Enter your domain (e.g. example.com): ").strip()
        if not domain:
            print_message("err", "Domain name required for Let's Encrypt/Cloudflare")
            sys.exit(1)
        email = input("Enter your email for Let's Encrypt: ").strip()
        if not email:
            email = "admin@" + domain
    if choice == "3":
        cloudflare_email = input("Enter Cloudflare account email: ").strip()
        cloudflare_api_token = input("Enter Cloudflare API Token: ").strip()
    if choice == "1":
        domain = "docker.localhost"
    return choice, domain, email, cloudflare_email, cloudflare_api_token

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

def get_user_input() ->  str | None:
    """Get user input interactively"""
    print_message("status", "Traefik Setup Configuration")
    print("==================================")
    
    test_domain = input("Enter test domain/subdomain (optional, e.g., test.yourdomain.com): ").strip()
    if not test_domain:
        test_domain = None
    
    if test_domain:
        confirm = input("Test page will auto-remove after 10 minutes. Continue? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print_message("status", "Setup cancelled.")
            sys.exit(0)
    
    return test_domain

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

def create_docker_compose(resolver_choice: str, domain: str, email: str, cf_email: str | None, cf_token: str | None):
    with open(HTPASSWD_FILE) as f:
        auth_hash = f.read().strip()

    resolver_config = ""
    if resolver_choice == "2":  # Let's Encrypt
        resolver_config = f"""
      - "--certificatesresolvers.le.acme.email={email}"
      - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
      - "--certificatesresolvers.le.acme.httpchallenge.entrypoint=web"
      - "--entrypoints.websecure.http.tls.certresolver=le"
"""
    elif resolver_choice == "3":  # Cloudflare
        resolver_config = f"""
      - "--certificatesresolvers.cf.acme.email={email}"
      - "--certificatesresolvers.cf.acme.storage=/letsencrypt/acme.json"
      - "--certificatesresolvers.cf.acme.dnschallenge.provider=cloudflare"
      - "--certificatesresolvers.cf.acme.dnschallenge.delaybeforecheck=0"
      - "--entrypoints.websecure.http.tls.certresolver=cf"
    environment:
      - CF_API_EMAIL={cf_email}
      - CF_DNS_API_TOKEN={cf_token}
"""

    compose = f"""services:
  traefik:
    image: traefik:v3.4
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    networks:
      - proxy
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./certs:/certs:ro
      - ./dynamic:/dynamic:ro
      - ./letsencrypt:/letsencrypt
    command:
      - "--entrypoints.web.address=:80"
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
      - "--entrypoints.web.http.redirections.entrypoint.permanent=true"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.websecure.http.tls=true"
      - "--providers.file.filename=/dynamic/tls.yaml"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--providers.docker.network=proxy"
      - "--api.dashboard=true"
      - "--api.insecure=false"
      - "--log.level=INFO"
      - "--accesslog=true"
      - "--metrics.prometheus=true"{resolver_config}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.dashboard.rule=Host(`traefik.{domain}`)"
      - "traefik.http.routers.dashboard.entrypoints=websecure"
      - "traefik.http.routers.dashboard.service=api@internal"
      - "traefik.http.routers.dashboard.tls=true"
      - "traefik.http.middlewares.dashboard-auth.basicauth.users={auth_hash}"
      - "traefik.http.routers.dashboard.middlewares=dashboard-auth@docker"

networks:
  proxy:
    name: proxy
"""
    _ = Path(COMPOSE_FILE).write_text(compose)
    print_message("ok", f"Docker Compose file created at {COMPOSE_FILE}")

def create_test_compose(domain: str | None) -> None:
    """Create test page Docker Compose file using Nginx with a custom page"""
    if not domain:
        return
    
    # Use the global test compose path
    Path(TEST_COMPOSE_PATH).mkdir(parents=True, exist_ok=True)
    
    # Create index.html with proper escaping
    index_content = f"<h1>Traefik + Nginx Test Page</h1><p>Domain: test.{domain}</p>"
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
      - "traefik.http.routers.nginx-test.rule=Host(`test.{domain}`)"
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

def display_final_info(domain: str | None) -> None:
    """Display final setup information"""
    print_message("success", "Traefik setup completed!")
    print("")
    print("Summary:")
    print("--------")
    print(f"• Docker Compose files: {TRAEFIK_BASE_PATH}/")
    print("• Docker network: traefik")
    print("")
    
    if domain:
        print("🎉 Your test page is available at:")
        print(f"  • https://test.{domain}")
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
    if domain:
        print("\nAccess URLs:")
        print(f"  Dashboard → https://traefik.{domain}")
        print(f"  Test page    → https://test.{domain}")
        print("Use your Basic Auth credentials when prompted.")
    print("")
    
    if domain:
        print("To manually remove test page early:")
        print(f"  docker compose -f {TEST_COMPOSE_PATH}/docker-compose-test.yml down")

def main() -> None:
    """Main setup function"""
    print_message("status", "Starting automated Traefik setup...")
    
    # Check prerequisites
    check_docker()
    
    # Setup
    ensure_dirs()
    resolver_choice, domain, email, cf_email, cf_token = ask_for_resolver()
    create_self_signed_cert(domain)
    create_htpasswd()
    create_dynamic_tls()
    create_docker_compose(resolver_choice, domain, email, cf_email, cf_token)
    create_test_compose(domain)
    setup_docker_network()
    
    # Deploy
    deploy_traefik()
    deploy_test_page(domain)
    
    # Final info
    display_final_info(domain)
    print_message("success", "Setup complete! 🎉")

if __name__ == "__main__":
    main()