import time
import threading
from collections import deque
import psutil
from src.database import SessionLocal, Settings

class RateLimiter:
    """
    Manages rate limits for AI requests.
    Uses a simple sliding window (Token Bucket approximation).
    """
    _request_timestamps = deque()
    _lock = threading.Lock()

    @classmethod
    def can_proceed(cls):
        """
        Checks if a new request can be made based on settings and history.
        """
        with cls._lock:
            # 1. Clean old timestamps (> 1 hour)
            now = time.time()
            while cls._request_timestamps and now - cls._request_timestamps[0] > 3600:
                cls._request_timestamps.popleft()

            # 2. Get Limit from DB
            db = SessionLocal()
            try:
                settings = db.query(Settings).first()
                limit = settings.max_ai_requests_per_hour if settings else 10
            finally:
                db.close()

            # 3. Check count
            if len(cls._request_timestamps) >= limit:
                return False

            return True

    @classmethod
    def record_request(cls):
        """
        Records a successful request.
        """
        with cls._lock:
            cls._request_timestamps.append(time.time())

class ResourceGuard:
    """
    Checks system health before heavy ops.
    """
    @staticmethod
    def is_safe(cpu_threshold=85, mem_threshold=85):
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
            if cpu > cpu_threshold or mem > mem_threshold:
                return False
            return True
        except:
            return True # Fail open if psutil missing
