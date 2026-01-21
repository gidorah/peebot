import json
import logging
import threading
import requests
from django.conf import settings


class SeqHandler(logging.Handler):
    def __init__(self, server_url, api_key=None, batch_size=1, static_fields=None):
        super().__init__()
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.static_fields = static_fields or {}
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-Seq-ApiKey": api_key})
        self.session.headers.update({"Content-Type": "application/vnd.serilog.clef"})

    def emit(self, record):
        try:
            # Format the log record using the configured formatter (returns a dict if using JSONRenderer)
            payload_data = self.format(record)

            # If payload_data is a string (JSON), parse it back to dict to add static fields
            # This is a bit inefficient but ensures we can inject our service tags
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

            # We run this in a thread to avoid blocking the main execution
            threading.Thread(target=self._send, args=(final_payload,)).start()

        except Exception:
            self.handleError(record)

    def _send(self, payload):
        try:
            # Seq raw events endpoint
            url = f"{self.server_url}/api/events/raw?clef"
            self.session.post(url, data=payload, timeout=2)
        except Exception as e:
            # Print error in dev so we know if connection fails
            print(f"SEQ LOGGING ERROR: {e}")
