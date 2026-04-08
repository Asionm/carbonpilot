import uvicorn
import os
import subprocess
import signal
import sys
import shutil
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

from server.main import app

def start_frontend():
    """Start the Next.js frontend development server"""
    try:
        # Check if npm is available
        npm_executable = None
        if sys.platform.startswith("win"):
            # On Windows, try both npm and npm.cmd
            if shutil.which("npm.cmd"):
                npm_executable = "npm.cmd"
            elif shutil.which("npm"):
                npm_executable = "npm"
        else:
            # On Unix-like systems
            if shutil.which("npm"):
                npm_executable = "npm"
        
        if not npm_executable:
            print("Warning: npm is not installed or not in PATH. Skipping frontend server start.")
            print("Please install Node.js from https://nodejs.org to run the frontend.")
            return None
            
        # Check if we're in the right directory
        if not os.path.exists("web"):
            print("Error: Please run this script from the project root directory (web directory not found)")
            return None
            
        # Check if node_modules exists in web directory
        if not os.path.exists("web/node_modules"):
            print("Installing frontend dependencies...")
            try:
                install_result = subprocess.run(
                    [npm_executable, "install"],
                    cwd="./web",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=300  # 5 minutes timeout
                )
                if install_result.returncode != 0:
                    print("Error installing dependencies:")
                    print(install_result.stderr.decode())
                    return None
                print("Dependencies installed successfully!")
            except subprocess.TimeoutExpired:
                print("Timeout while installing dependencies. Please try again.")
                return None
            except Exception as e:
                print(f"Error during dependency installation: {e}")
                return None
            
        # Change to the web directory and start the Next.js dev server
        frontend_process = subprocess.Popen(
            [npm_executable, "run", "dev"],
            cwd="./web",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print("Frontend server starting on http://localhost:3000")
        return frontend_process
    except Exception as e:
        print(f"Error starting frontend server: {e}")
        print("Please make sure Node.js is installed and npm is in your PATH.")
        print("You can manually start the frontend by running 'npm run dev' in the web directory.")
        return None

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    print("\nShutting down servers...")
    sys.exit(0)

def print_startup_info():
    """Print helpful startup information"""
    print("=" * 60)
    print("CarbonPilot - AI-Powered Carbon Emission Analysis Tool")
    print("=" * 60)
    print("Backend server will start on: http://localhost:8000")
    print("Frontend server should start on: http://localhost:3000")
    print()
    print("If frontend doesn't start:")
    print("1. Make sure Node.js is installed from https://nodejs.org")
    print("2. Install frontend dependencies with: cd web && npm install")
    print("3. Manually start frontend with: cd web && npm run dev")
    print("=" * 60)

if __name__ == "__main__":
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    load_dotenv(override=True)
    
    # Print startup information
    print_startup_info()
    
    # Start frontend server in a separate process
    frontend_process = start_frontend()
    
    # Start backend server
    port = int(os.getenv("SERVER_PORT", 8000))
    print(f"Backend server starting on http://localhost:{port}")
    
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=False)