import subprocess
import sys
import os
import platform

def run(cmd):
    print(f">> Running: {cmd}")
    subprocess.check_call(cmd, shell=True)

def main():
    # 0. Version check
    if sys.version_info >= (3, 12):
        print("!! WARNING: You are running Python 3.12+.")
        print("!! Machine learning dependencies (like TensorFlow/DeepFace) are most stable on Python 3.11.")
        print("!! While we include workarounds, you may encounter issues on this version.")
        try:
            cont = input(">> Continue anyway? [y/N]: ").lower()
            if cont != 'y':
                sys.exit(1)
        except EOFError:
            print("\nAborting.")
            sys.exit(1)

    # 1. Create venv
    print("--- Creating Virtual Environment ---")
    run(f"{sys.executable} -m venv .venv")
    
    # 2. Path to venv python
    if platform.system() == "Windows":
        py = os.path.join(".venv", "Scripts", "python.exe")
    else:
        py = os.path.join(".venv", "bin", "python")

    # 3. Upgrade pip
    run(f"{py} -m pip install --upgrade pip")

    # 4. Install requirements
    print("\n--- Installing Dependencies (Core + AI) ---")
    run(f"{py} -m pip install -r requirements.txt")
    run(f"{py} -m pip install -r requirements-optional.txt")

    # 5. Prefetch models
    print("\n--- Downloading AI Models (Whisper, Emotion, etc.) ---")
    run(f"{py} scripts/prefetch_models.py")

    # 6. Pull Ollama model
    print("\n--- Pulling Llama 3.2 via Ollama ---")
    try:
        run("ollama pull llama3.2:3b")
    except Exception:
        print("!! WARNING: Could not pull Ollama model. Is Ollama running?")

    print("\n" + "="*50)
    print("SETUP COMPLETE!")
    print("To start the journal, run:")
    if platform.system() == "Windows":
        print("  .venv\\Scripts\\activate")
    else:
        print("  source .venv/bin/activate")
    print("  python run.py")
    print("="*50)

if __name__ == "__main__":
    main()
