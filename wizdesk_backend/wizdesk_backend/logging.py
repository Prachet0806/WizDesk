"""JSON lines for application logs consumed by the deployment platform."""

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            event["exception_type"] = record.exc_info[0].__name__
        return json.dumps(event, ensure_ascii=False)
