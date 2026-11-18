from threading import get_ident
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock, patch

from django.db import connections

from nabd.i18n import Config


def _connection(alias, age=0, opened=False, atomic=False, autocommit=True):
    conn = Mock(
        alias=alias,
        connection=object() if opened else None,
        settings_dict={"CONN_MAX_AGE": age},
        in_atomic_block=atomic,
    )
    conn.get_autocommit.return_value = autocommit
    return conn


class SingletonModelTest(TestCase):
    def test_failed_load_closes_only_new_transient_connections(self):
        existing = _connection("existing", opened=True)
        new = _connection("default")
        persistent = _connection("persistent", age=60)
        unbounded = _connection("unbounded", age=None)
        atomic = _connection("atomic", atomic=True)
        transaction = _connection("transaction", autocommit=False)
        unused = _connection("unused")
        opened = [new, persistent, unbounded, atomic, transaction]

        def failed_load():
            for conn in opened:
                conn.connection = object()
            raise RuntimeError("query failed")

        with (
            patch.object(
                connections, "all", return_value=[existing, *opened, unused]
            ),
            patch.object(Config, "load", side_effect=failed_load),
            self.assertRaisesRegex(RuntimeError, "query failed"),
        ):
            Config.load_once()

        new.close.assert_called_once_with()
        for conn in (
            existing,
            persistent,
            unbounded,
            atomic,
            transaction,
            unused,
        ):
            conn.close.assert_not_called()


class SingletonModelAsyncTest(IsolatedAsyncioTestCase):
    async def test_async_operations_close_on_the_database_thread(self):
        instance = Config()
        conn = _connection("default")
        operation_threads = []
        cleanup_threads = []

        def access(*args, **kwargs):
            conn.connection = object()
            operation_threads.append(get_ident())
            return instance

        def close():
            cleanup_threads.append(get_ident())
            conn.connection = None

        conn.close.side_effect = close
        with (
            patch.object(connections, "all", return_value=[conn]),
            patch.object(Config, "load", side_effect=access),
            patch.object(instance, "save", side_effect=access) as save,
        ):
            self.assertIs(await Config.load_async(), instance)
            await instance.save_async(update_fields=["locale"])

        save.assert_called_once_with(update_fields=["locale"])
        self.assertEqual(len(cleanup_threads), 2)
        self.assertEqual(cleanup_threads, operation_threads)
        self.assertNotIn(get_ident(), cleanup_threads)
