import asyncio
from typing import List

class LabLogger:
    _instance = None
    _clients = set()
    _log_history: List[str] = []
    _main_loop = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LabLogger, cls).__new__(cls)
        return cls._instance

    @classmethod
    def set_loop(cls, loop):
        cls._main_loop = loop

    @classmethod
    async def _broadcast(cls, message: str):
        if not cls._clients:
            return

        dead = set()
        for client in cls._clients:
            try:
                await client.send_text(message)
            except:
                dead.add(client)
        cls._clients -= dead

    @classmethod
    async def log(cls, category: str, message: str):
        """
        Logs a message and broadcasts it to connected clients.
        Category: 'UI', 'API', 'AI', 'DB', 'SYSTEM'
        """
        import time
        import asyncio
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{category}] {message}"
        print(entry) # Standard stdout

        # Store in history (limit 100)
        cls._log_history.append(entry)
        if len(cls._log_history) > 100:
            cls._log_history.pop(0)

        # Broadcast Thread-Safe
        if cls._main_loop and cls._main_loop.is_running():
            try:
                # If we are in the main loop, await directly?
                # Check current loop
                try:
                    curr = asyncio.get_running_loop()
                    if curr == cls._main_loop:
                        await cls._broadcast(entry)
                        return
                except RuntimeError:
                    pass

                # If different thread, schedule it
                asyncio.run_coroutine_threadsafe(cls._broadcast(entry), cls._main_loop)
            except Exception as e:
                print(f"Logger Error: {e}")
        else:
            # Fallback if loop not set (e.g. tests)
            pass

    @classmethod
    def get_history(cls):
        return cls._log_history

    @classmethod
    def add_client(cls, websocket):
        cls._clients.add(websocket)

    @classmethod
    def remove_client(cls, websocket):
        cls._clients.remove(websocket)
