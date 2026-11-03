import json
import logging

from django.test import SimpleTestCase

from wizdesk_backend.logging import JsonFormatter


class StructuredLoggingTests(SimpleTestCase):
    def test_application_event_is_one_json_object(self):
        record = logging.LogRecord(
            name="users.views",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="Password reset delivery failed",
            args=(),
            exc_info=None,
        )
        event = json.loads(JsonFormatter().format(record))
        self.assertEqual(event["level"], "WARNING")
        self.assertEqual(event["logger"], "users.views")
        self.assertEqual(event["message"], "Password reset delivery failed")
        self.assertIn("timestamp", event)
