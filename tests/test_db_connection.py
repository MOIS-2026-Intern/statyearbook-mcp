# -*- coding: utf-8 -*-
"""app이 현재 프로필의 DSN으로 DB 커넥션을 여는지 검증한다."""
import unittest
from unittest.mock import patch

from psycopg.rows import dict_row

from app.config import settings
from app.db import ObservedCursor, connect


class DatabaseConnectionTests(unittest.TestCase):
    # 커넥션은 프로필 DSN을 dict 행과 관측 커서 설정으로 열어야 한다.
    def test_connect_opens_configured_dsn_with_dict_rows(self) -> None:
        with patch("app.db.psycopg.connect") as connect_mock:
            connection = connect()

        self.assertTrue(settings.dsn.startswith("postgresql"))
        connect_mock.assert_called_once_with(
            settings.dsn,
            row_factory=dict_row,
            cursor_factory=ObservedCursor,
        )
        self.assertIs(connection, connect_mock.return_value)


if __name__ == "__main__":
    unittest.main()
