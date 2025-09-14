from decouple import config

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./email_threads.db")
AZURE_OPENAI_CHAT_ENDPOINT = config("AZURE_OPENAI_CHAT_ENDPOINT", default="")
AZURE_OPENAI_CHAT_API_KEY = config("AZURE_OPENAI_CHAT_API_KEY", default="")
AZURE_OPENAI_CHAT_DEPLOYMENT = config("AZURE_OPENAI_CHAT_DEPLOYMENT", default="gpt-5-mini")
AZURE_OPENAI_CHAT_API_VERSION = config("AZURE_OPENAI_CHAT_API_VERSION", default="2025-01-01-preview")
LOG_LEVEL = config("LOG_LEVEL", default="INFO")
