"""Structured-logging handler that forwards events to a Seq server.

PeeBot uses Structlog + Seq for centralized structured logging in
development (ADR-006). This module provides ``SeqHandler`` — a standard
``logging.Handler`` that serializes records as CLEF (Compact Log Event
Format) and POSTs them to Seq's raw-events endpoint on a background
thread, so the main request/worker loop is never blocked on HTTP I/O.

In production the Seq handler is not installed (ADR-013): logs go straight
to stdout via structlog's ``ConsoleRenderer`` and are captured by Docker.
"""

import json
import logging
import queue
import sys
import threading
from typing import Any

import requests


class SeqHandler(logging.Handler):
    """Async-dispatching logging handler that ships records to Seq.

    The handler buffers formatted CLEF payloads in an internal
    ``queue.Queue`` (bounded at 5000 entries) and drains them on a daemon
    worker thread. When the queue is full, new events are dropped to stderr
    rather than blocking the caller — preserving the principle that logging
    must never stall the hot path.

    Static fields (e.g. ``{"Application": "peebot-web"}``) are merged into
    every event so Seq searches can scope by service/environment.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        static_fields: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the handler and start its background worker thread.

        Args:
            server_url: Base URL of the Seq server (e.g. ``http://seq:5341``).
                A trailing slash is tolerated and stripped.
            api_key: Optional Seq API key; when provided it is attached as
                the ``X-Seq-ApiKey`` request header on every POST.
            static_fields: Optional dict merged into every event before
                dispatch — used to tag logs with service name and
                environment per ADR-006.
        """
        super().__init__()
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.static_fields = static_fields or {}
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-Seq-ApiKey": api_key})
        self.session.headers.update({"Content-Type": "application/vnd.serilog.clef"})

        self.queue: queue.Queue[str] = queue.Queue(maxsize=5000)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker, name="SeqLoggerWorker", daemon=True
        )
        self._worker_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        """Format ``record`` into CLEF JSON and enqueue it for dispatch.

        Static fields are merged into the payload before serialization so
        downstream searches can filter by service/environment without
        every call site having to set them.

        If the queue is full (producer outpacing Seq), the event is dropped
        and a single line is written to stderr. Any unexpected exception is
        routed through ``Handler.handleError`` so a broken Seq connection
        cannot take down the application.
        """
        try:
            payload_data = self.format(record)

            if isinstance(payload_data, str):
                try:
                    event_dict = json.loads(payload_data)
                except json.JSONDecodeError:
                    event_dict = {"@m": payload_data}
            else:
                event_dict = payload_data

            event_dict.update(self.static_fields)

            final_payload = json.dumps(event_dict)

            try:
                self.queue.put_nowait(final_payload)
            except queue.Full:
                sys.stderr.write("SeqHandler queue full, dropping log.\n")

        except Exception:
            self.handleError(record)

    def _worker(self) -> None:
        """Consume queued payloads and POST them to Seq until stopped."""
        while not self._stop_event.is_set():
            try:
                payload = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            self._send(payload)
            self.queue.task_done()

    def close(self) -> None:
        """Flush remaining queued events, stop the worker, and close the session.

        Drains the queue synchronously before signalling shutdown so that
        events captured right before process exit (e.g. during signal
        handling) still reach Seq — up to a 1-second join budget for the
        worker thread.
        """
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
        """POST a single CLEF payload to Seq's raw-events endpoint.

        Failures are printed to stdout so dev environments surface Seq
        outages loudly; we deliberately do not re-raise because logging
        must not crash the caller.
        """
        try:
            url = f"{self.server_url}/api/events/raw?clef"
            self.session.post(url, data=payload, timeout=2)
        except Exception as e:
            print(f"SEQ LOGGING ERROR: {e}")
