
import unittest
from unittest.mock import MagicMock, patch
import json
import os
import sys

# Mocking os.environ to avoid issues with DATABASE_URL
with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/db"}):
    import app

class TestEvoWebhook(unittest.TestCase):
    @patch('app.update_device_communication')
    def test_evo_webhook_updates_comm(self, mock_update):
        mock_ws = MagicMock()
        # Mock receiving a 'reg' message with SN
        # Use a list for side_effect to simulate multiple calls to receive()
        mock_ws.receive.side_effect = [
            json.dumps({"cmd": "reg", "sn": "EVO999", "v": "1.0"}),
            Exception("Stop loop") # To break the while True loop
        ]

        # Access the function directly. If decorated by flask-sock,
        # it might be in different places depending on version.
        # Let's try to find it.
        func = app.evo_webhook
        print(f"Type of app.evo_webhook: {type(func)}")

        try:
            # If it's the original function, this should work.
            # If it's decorated, we might need to find the original.
            func(mock_ws)
        except Exception as e:
            if "Stop loop" not in str(e):
                self.fail(f"Unexpected exception: {e}")

        mock_update.assert_called_with("EVO999")

if __name__ == '__main__':
    unittest.main()
