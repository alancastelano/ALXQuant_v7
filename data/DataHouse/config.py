from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


@dataclass
class Config:
    fred_api_key: str = os.getenv("FRED_API_KEY", "")
    processed_dir: str = os.path.join(os.path.dirname(__file__), "..", "processed")


config = Config()
