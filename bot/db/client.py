import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(dotenv_path="config/.env")

sb: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)
