import json
import hashlib
import os
from pathlib import Path

class CacheService:
    def __init__(self, cache_dir=".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def get_cache_key(self, text, sender):
        return hashlib.md5(f"{sender}:{text}".encode()).hexdigest()

    def get(self, text, sender):
        key = self.get_cache_key(text, sender)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            with open(cache_file, "r") as f:
                return json.load(f)
        return None

    def set(self, text, sender, data):
        key = self.get_cache_key(text, sender)
        cache_file = self.cache_dir / f"{key}.json"
        with open(cache_file, "w") as f:
            json.dump(data, f)
