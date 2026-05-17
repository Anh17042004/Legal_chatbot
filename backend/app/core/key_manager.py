import threading
from app.core.config import settings

class APIKeyManager:
    def __init__(self, keys_str: str):
        if not keys_str:
            self.keys = []
        else:
            self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        
        self._current_idx = 0
        self._lock = threading.Lock()

    def get_next_key(self) -> str:
        #Lấy key tiếp theo theo thuật toán Round-Robin (Thread-safe).
        if not self.keys:
            return ""
            
        with self._lock:
            key = self.keys[self._current_idx]
            self._current_idx = (self._current_idx + 1) % len(self.keys)
            return key


ollama_key_manager = APIKeyManager(settings.OLLAMA_API_KEY)
cohere_key_manager = APIKeyManager(settings.COHERE_API_KEYS)
