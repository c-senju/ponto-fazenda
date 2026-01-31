
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import sys
import os

# Mocking os.environ to avoid issues with DATABASE_URL
with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/db"}):
    # Import app after mocking
    import app

class TestDeviceStatus(unittest.TestCase):
    @patch('app.get_db_connection')
    def test_update_device_communication(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        sn = "EVO12345"
        app.update_device_communication(sn)

        # Check if execute was called with correct SQL
        args, kwargs = mock_cur.execute.call_args
        sql = args[0]
        params = args[1]

        self.assertIn("INSERT INTO dispositivos", sql)
        self.assertIn("ON CONFLICT (sn) DO UPDATE", sql)
        self.assertEqual(params[0], sn)
        self.assertIsInstance(params[1], datetime)

        mock_conn.commit.assert_called_once()
        mock_cur.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('app.get_db_connection')
    def test_index_last_comm_retrieval(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Mocking the MAX(last_communication) result
        expected_time = datetime(2024, 5, 23, 10, 0, 0)
        mock_cur.fetchone.side_effect = [(expected_time,), []] # First for devices, second for registros (mocking empty)

        # We need to mock the session as well
        with app.app.test_request_context():
            with patch('app.session', {'logged_in': True}):
                with patch('app.render_template') as mock_render:
                    app.index()
                    # Check if last_evo_comm was passed correctly
                    args, kwargs = mock_render.call_args
                    self.assertEqual(kwargs['last_evo_comm'], expected_time)

if __name__ == '__main__':
    unittest.main()
