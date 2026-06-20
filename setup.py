import urllib.request
import json
import os
import sys

def get_ollama_models():
    """Fetch available models from the local Ollama instance."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            return [model['name'] for model in data.get('models', [])]
    except Exception:
        return []

def main():
    print("="*50)
    print("🕵️ OSINT-V1 Setup Wizard")
    print("="*50)
    
    env_lines = []
    
    # Read existing .env if it exists to preserve other configs? 
    # For a simple setup, we'll just overwrite or append LLM configs.
    # To be safe, we'll create a dictionary of new settings, read old, merge, and write.
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    print("\nSelect your primary LLM Provider:")
    print("1. Ollama (Local, Free, Privacy-focused)")
    print("2. Gemini (Google)")
    print("3. OpenAI (GPT-4, Groq, LM Studio, etc.)")
    
    choice = input("\nEnter your choice (1/2/3) [1]: ").strip() or "1"
    
    provider_map = {"1": "ollama", "2": "gemini", "3": "openai"}
    provider = provider_map.get(choice, "ollama")
    
    env_vars["LLM_PROVIDER"] = provider
    env_vars["OLLAMA_IS_BEING_USED"] = str(provider == "ollama")
    env_vars["GEMINI_IS_BEING_USED"] = str(provider == "gemini")
    env_vars["OPENAI_IS_BEING_USED"] = str(provider == "openai")
    
    if provider == "gemini":
        key = input("Enter your Gemini API Key: ").strip()
        if key: env_vars["GEMINI_API_KEY"] = key
        
        model = input("Enter Gemini Model [gemini-1.5-flash]: ").strip() or "gemini-1.5-flash"
        env_vars["GEMINI_MODEL"] = model
        
    elif provider == "openai":
        key = input("Enter your OpenAI API Key: ").strip()
        if key: env_vars["OPENAI_API_KEY"] = key
        
        base_url = input("Enter OpenAI Base URL [https://api.openai.com/v1]: ").strip() or "https://api.openai.com/v1"
        env_vars["OPENAI_BASE_URL"] = base_url
        
        model = input("Enter OpenAI Model [gpt-4o-mini]: ").strip() or "gpt-4o-mini"
        env_vars["OPENAI_MODEL"] = model
        
    elif provider == "ollama":
        print("\nDetecting installed Ollama models...")
        models = get_ollama_models()
        if models:
            print("\nFound the following models:")
            for i, m in enumerate(models, 1):
                print(f"{i}. {m}")
            m_choice = input(f"\nSelect a model (1-{len(models)}) [1]: ").strip() or "1"
            try:
                idx = int(m_choice) - 1
                if 0 <= idx < len(models):
                    selected_model = models[idx]
                else:
                    selected_model = models[0]
            except ValueError:
                selected_model = models[0]
            print(f"Selected model: {selected_model}")
            env_vars["OLLAMA_MODEL"] = selected_model
            
            # Serialize the list of models as JSON string for Pydantic
            models_json = json.dumps(models)
            env_vars["AVAILABLE_OLLAMA_MODELS"] = models_json
        else:
            print("Could not connect to Ollama (is it running?).")
            model = input("Enter Ollama Model manually [qwen2.5:3b]: ").strip() or "qwen2.5:3b"
            env_vars["OLLAMA_MODEL"] = model

    # 3. Tor Configuration
    print("\n[Tor Configuration]")
    tor_default = "C:\\Program Files\\Tor\\tor\\tor.exe" if os.name == 'nt' else "/usr/bin/tor"
    tor_path = input(f"Enter path to Tor executable [{tor_default}]: ").strip() or tor_default
    env_vars["TOR_EXECUTABLE_PATH"] = tor_path

    # Write back to .env
    with open(".env", "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
            
    print("\n✅ Setup complete! Configuration saved to .env")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        sys.exit(1)
