import os


DEFAULT_API_BASE_URL = "https://child-safety-app-6s5b.onrender.com"
API_BASE_URL = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL).strip()
