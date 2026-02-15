import json
import logging
import queue
import sys
import threading
from typing import Any

import requests


class SeqHandler(logging.Handler):
    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        static_fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.static_fields = static_fields or {}
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-Seq-ApiKey": api_key})
        self.session.headers.update({"Content-Type": "application/vnd.serilog.clef"})

        # Initialize queue and worker
        self.queue: queue.Queue[str] = queue.Queue(maxsize=5000)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker, name="SeqLoggerWorker", daemon=True
        )
        self._worker_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Format the log record using the configured formatter
            # (returns a dict if using JSONRenderer)
            payload_data = self.format(record)

            # If payload_data is a string (JSON), parse it back to dict
            # to add static fields. This is inefficient but ensures
            # we can inject our service tags
            if isinstance(payload_data, str):
                try:
                    event_dict = json.loads(payload_data)
                except json.JSONDecodeError:
                    # Fallback if it's just a raw string
                    event_dict = {"@m": payload_data}
            else:
                event_dict = payload_data

            # Merge static fields (e.g. {"Application": "peebot-web"})
            event_dict.update(self.static_fields)

            # Re-serialize to JSON
            final_payload = json.dumps(event_dict)

            # Push to queue instead of spawning a thread
            try:
                self.queue.put_nowait(final_payload)
            except queue.Full:
                # Drop log if queue is full to prevent blocking main thread or crashing
                sys.stderr.write("SeqHandler queue full, dropping log.\n")

        except Exception:
            self.handleError(record)

    def _worker(self) -> None:
        """Background worker to consume logs from the queue and send to Seq."""
        while not self._stop_event.is_set():
            try:
                payload = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            self._send(payload)
            self.queue.task_done()

    def close(self) -> None:
        """Signal worker to stop and wait briefly."""
        # Drain any remaining logs in the queue
        while True:
            try:
                payload = self.queue.get_nowait()
                self._send(payload)
                self.queue.task_done()
            except queue.Empty:
                break

        self._stop_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

        self.session.close()
        super().close()

    def _send(self, payload: str) -> None:
        try:
            # Seq raw events endpoint
            url = f"{self.server_url}/api/events/raw?clef"
            self.session.post(url, data=payload, timeout=2)
        except Exception as e:
            # Print error in dev so we know if connection fails
            print(f"SEQ LOGGING ERROR: {e}")
