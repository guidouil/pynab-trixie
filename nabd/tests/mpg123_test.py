import ctypes as c
import unittest
from unittest.mock import Mock, patch

from nabd import mpg123


class TestMpg123(unittest.TestCase):
    def setUp(self):
        self.lib = Mock()
        for name in ("init", "open_64", "open_feed", "feed"):
            getattr(self.lib, "mpg123_" + name).return_value = mpg123.OK
        del self.lib.mpg123_open
        self.lib.mpg123_new.return_value = 0x123456789
        self.lib.mpg123_plain_strerror.return_value = b"decoder failure"
        self.lib.mpg123_encsize.return_value = 2
        self.lib.mpg123_length64.return_value = 2**40
        self.lib.mpg123_decode_frame64.return_value = mpg123.DONE
        for target, value in (
            ("_library", None),
            ("find_library", Mock(return_value="libmpg123.so.0")),
            ("c.CDLL", Mock(return_value=self.lib)),
        ):
            patcher = patch("nabd.mpg123." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_file_and_64_bit_abi(self):
        pcm = c.create_string_buffer(b"\x01\0\x02\0")
        results = iter((mpg123.NEW_FORMAT, mpg123.OK, mpg123.DONE))

        def decode(handle, number, audio, size):
            self.assertIsInstance(number._obj, c.c_int64)
            self.assertIsInstance(size._obj, c.c_size_t)
            number._obj.value = 2**40
            c.cast(audio, c.POINTER(c.c_void_p))[0] = c.addressof(pcm)
            size._obj.value = 4
            return next(results)

        def get_format(handle, rate, channels, encoding):
            self.assertIsInstance(rate._obj, c.c_long)
            rate._obj.value = 44100
            channels._obj.value = 1
            encoding._obj.value = 0xD0
            return mpg123.OK

        self.lib.mpg123_decode_frame64.side_effect = decode
        self.lib.mpg123_getformat.side_effect = get_format
        with mpg123.Mpg123("heure.mp3") as decoder:
            self.assertEqual(decoder.get_format(), (44100, 1, 0xD0))
            self.assertEqual(decoder.get_width_by_encoding(0xD0), 2)
            self.assertEqual(decoder.length(), 2**40)
            self.assertEqual(list(decoder.iter_frames()), [b"\x01\0\x02\0"])
        decoder.close()
        self.lib.mpg123_open_64.assert_called_once_with(
            0x123456789, b"heure.mp3"
        )
        self.assertIs(self.lib.mpg123_new.restype, c.c_void_p)
        self.assertIs(self.lib.mpg123_length64.restype, c.c_int64)
        self.assertEqual(
            self.lib.mpg123_decode_frame64.argtypes,
            [
                c.c_void_p,
                c.POINTER(c.c_int64),
                c.POINTER(c.POINTER(c.c_ubyte)),
                c.POINTER(c.c_size_t),
            ],
        )
        self.lib.mpg123_delete.assert_called_once_with(0x123456789)

    def test_feed_can_resume_after_need_more_and_init_is_once(self):
        pcm = c.create_string_buffer(b"pcm")
        results = iter((mpg123.NEED_MORE, mpg123.OK, mpg123.NEED_MORE))

        def decode(handle, number, audio, size):
            c.cast(audio, c.POINTER(c.c_void_p))[0] = c.addressof(pcm)
            size._obj.value = 3
            return next(results)

        self.lib.mpg123_decode_frame64.side_effect = decode
        with mpg123.Mpg123() as decoder:
            self.assertEqual(list(decoder.iter_frames()), [])
            decoder.feed(b"mp3\0data")
            self.assertEqual(list(decoder.iter_frames()), [b"pcm"])
        with mpg123.Mpg123():
            pass
        self.lib.mpg123_feed.assert_called_once_with(
            0x123456789, b"mp3\0data", 8
        )
        self.lib.mpg123_init.assert_called_once_with()
        self.assertEqual(self.lib.mpg123_delete.call_count, 2)

    def test_native_open_without_large_file_suffix(self):
        del self.lib.mpg123_open_64
        self.lib.mpg123_open = Mock(return_value=mpg123.OK)
        with mpg123.Mpg123("heure.mp3"):
            pass
        self.lib.mpg123_open.assert_called_once_with(0x123456789, b"heure.mp3")
        self.assertEqual(
            self.lib.mpg123_open.argtypes, [c.c_void_p, c.c_char_p]
        )

    def test_open_failure_deletes_handle(self):
        self.lib.mpg123_open_64.return_value = -1
        with self.assertRaisesRegex(RuntimeError, "decoder failure"):
            mpg123.Mpg123("missing.mp3")
        self.lib.mpg123_delete.assert_called_once_with(0x123456789)

    def test_failed_allocation_does_not_delete_null_handle(self):
        self.lib.mpg123_new.return_value = None
        with self.assertRaisesRegex(RuntimeError, "decoder failure"):
            mpg123.Mpg123()
        self.lib.mpg123_delete.assert_not_called()

    def test_operation_failures_still_close(self):
        operations = (
            ("feed", lambda d: d.feed(b"mp3")),
            ("getformat", lambda d: d.get_format()),
            ("decode_frame64", lambda d: list(d.iter_frames())),
            ("length64", lambda d: d.length()),
        )
        for name, operation in operations:
            with self.subTest(name=name):
                function = getattr(self.lib, "mpg123_" + name)
                previous = function.return_value
                function.return_value = -1
                with self.assertRaisesRegex(RuntimeError, "decoder failure"):
                    with mpg123.Mpg123() as decoder:
                        operation(decoder)
                self.assertIsNone(decoder.handle)
                function.return_value = previous
        self.assertEqual(self.lib.mpg123_delete.call_count, len(operations))

    def test_initialization_failure_is_not_cached(self):
        self.lib.mpg123_init.return_value = -1
        with self.assertRaisesRegex(RuntimeError, "decoder failure"):
            mpg123.Mpg123()
        self.lib.mpg123_new.assert_not_called()
        self.assertIsNone(mpg123._library)


if __name__ == "__main__":
    unittest.main()
