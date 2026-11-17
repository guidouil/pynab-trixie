"""The libmpg123 1.32+ API used by Pynab, including 32-bit time64 systems."""

import ctypes as c
import os
from ctypes.util import find_library
from threading import Lock

OK, NEED_MORE, NEW_FORMAT, DONE = 0, -10, -11, -12
_library = None
_library_lock = Lock()


def _check(lib, result):
    if result != OK:
        raise RuntimeError(lib.mpg123_plain_strerror(result).decode())


def _get_library():
    global _library
    with _library_lock:
        if _library is None:
            path = find_library("mpg123")
            if not path:
                raise OSError("libmpg123 1.32+ is required")
            lib = c.CDLL(path)
            try:
                open_file = lib.mpg123_open_64
            except AttributeError:
                open_file = lib.mpg123_open
            open_file.restype = c.c_int
            open_file.argtypes = [c.c_void_p, c.c_char_p]
            for name, result, args in (
                ("init", c.c_int, []),
                ("new", c.c_void_p, [c.c_char_p, c.POINTER(c.c_int)]),
                ("delete", None, [c.c_void_p]),
                ("plain_strerror", c.c_char_p, [c.c_int]),
                ("open_feed", c.c_int, [c.c_void_p]),
                ("feed", c.c_int, [c.c_void_p, c.c_char_p, c.c_size_t]),
                (
                    "getformat",
                    c.c_int,
                    [
                        c.c_void_p,
                        c.POINTER(c.c_long),
                        c.POINTER(c.c_int),
                        c.POINTER(c.c_int),
                    ],
                ),
                ("encsize", c.c_int, [c.c_int]),
                (
                    "decode_frame64",
                    c.c_int,
                    [
                        c.c_void_p,
                        c.POINTER(c.c_int64),
                        c.POINTER(c.POINTER(c.c_ubyte)),
                        c.POINTER(c.c_size_t),
                    ],
                ),
                ("length64", c.c_int64, [c.c_void_p]),
            ):
                function = getattr(lib, "mpg123_" + name)
                function.restype, function.argtypes = result, args
            _check(lib, lib.mpg123_init())
            _library = lib, open_file
        return _library


class Mpg123:
    def __init__(self, filename=None):
        self.handle = None
        self._lib, open_file = _get_library()
        error = c.c_int()
        self.handle = self._lib.mpg123_new(None, c.byref(error))
        if not self.handle:
            raise RuntimeError(
                self._lib.mpg123_plain_strerror(error.value).decode()
            )
        try:
            if filename is None:
                result = self._lib.mpg123_open_feed(self.handle)
            else:
                result = open_file(self.handle, os.fsencode(filename))
            _check(self._lib, result)
        except BaseException:
            self.close()
            raise

    def feed(self, data):
        _check(self._lib, self._lib.mpg123_feed(self.handle, data, len(data)))

    def get_format(self):
        rate, channels, encoding = c.c_long(), c.c_int(), c.c_int()
        _check(
            self._lib,
            self._lib.mpg123_getformat(
                self.handle,
                c.byref(rate),
                c.byref(channels),
                c.byref(encoding),
            ),
        )
        return rate.value, channels.value, encoding.value

    def get_width_by_encoding(self, encoding):
        width = self._lib.mpg123_encsize(encoding)
        if width <= 0:
            raise RuntimeError("Unsupported libmpg123 sample encoding")
        return width

    def length(self):
        length = self._lib.mpg123_length64(self.handle)
        if length < 0:
            _check(self._lib, length)
        return length

    def iter_frames(self):
        # int64_t frame number is independent of the native size_t byte count.
        number, audio, size = c.c_int64(), c.POINTER(c.c_ubyte)(), c.c_size_t()
        while True:
            result = self._lib.mpg123_decode_frame64(
                self.handle, c.byref(number), c.byref(audio), c.byref(size)
            )
            if result == OK:
                yield c.string_at(audio, size.value)
            elif result in (NEED_MORE, DONE):
                return
            elif result != NEW_FORMAT:
                _check(self._lib, result)

    def close(self):
        if self.handle:
            self._lib.mpg123_delete(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()
