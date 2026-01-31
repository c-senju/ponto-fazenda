
import unittest
from unittest.mock import MagicMock, patch
import json
import os

# Mocking os.environ to avoid issues with DATABASE_URL
with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/db"}):
    import app

class TestEvoWebhook(unittest.TestCase):
    @patch('app.update_device_communication')
    def test_evo_webhook_updates_comm(self, mock_update):
        mock_ws = MagicMock()
        # Mock receiving a 'reg' message with SN
        mock_ws.receive.side_effect = [
            json.dumps({"cmd": "reg", "sn": "EVO999", "v": "1.0"}),
            Exception("Stop loop") # To break the while True loop
        ]

        try:
            app.evo_webhook(mock_ws)
        except Exception as e:
            if str(e) != "Stop loop":
                raise e

        mock_update.assert_called_with("EVO999")

if __name__ == '__main__':
    unittest.main()
