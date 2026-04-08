import asyncio
import json
import threading
from typing import Dict, AsyncGenerator
import logging

logger = logging.getLogger(__name__)

class SSEManager:
    def __init__(self):
        self.project_queues: Dict[str, asyncio.Queue] = {}
        self._lock = threading.Lock()
    
    async def add_client(self, project_name: str) -> asyncio.Queue:

        with self._lock:
            if project_name not in self.project_queues:
                self.project_queues[project_name] = asyncio.Queue()
            return self.project_queues[project_name]
    
    async def send_event(self, project_name: str, event_type: str, data: Dict):

        with self._lock:
            if project_name in self.project_queues:
                event = {
                    "event": event_type,
                    "data": data
                }
                await self.project_queues[project_name].put(event)
    
    async def stream_events(self, project_name: str) -> AsyncGenerator[str, None]:

        queue = await self.add_client(project_name)
        
        try:
            while True:
                event = await queue.get()

                yield f"event: {event['event']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
        except asyncio.CancelledError:

            logger.info(f"Client disconnected from project {project_name}")
        except Exception as e:
            logger.error(f"Error in SSE stream for project {project_name}: {e}")
        finally:

            with self._lock:
                if project_name in self.project_queues:
                    del self.project_queues[project_name]
    
    async def broadcast_event(self, event_type: str, data: Dict):

        with self._lock:
            for project_name in list(self.project_queues.keys()):
                await self.send_event(project_name, event_type, data)