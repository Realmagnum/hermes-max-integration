"""Win32 final-component no-follow open; called only by the owning I/O worker."""
from __future__ import annotations

import ctypes
import msvcrt
import ntpath
import os
from ctypes import wintypes


def open_regular(path: str) -> int:
    """Return a binary, non-inheritable CRT fd, or fail without reading data.

    Only ordinary local drive paths are supported. Reject namespaces/ADS/DOS
    devices *before* CreateFileW (a pipe/device open can itself block). As with
    POSIX O_NOFOLLOW, parent directories are trusted; the final component is not.
    The caller must fstat and compare its admitted dev/ino/size before any read.
    """
    path = os.fspath(path)
    if not isinstance(path, str) or path.startswith(("\\\\", "//")) or "\x00" in path:
        raise ValueError("Upload requires an ordinary local Windows path")
    path = ntpath.abspath(path)
    drive, tail = ntpath.splitdrive(path)
    if len(drive) != 2 or drive[1] != ":" or not drive[0].isascii() or not drive[0].isalpha():
        raise ValueError("Upload requires a local drive path")
    for component in tail.replace("/", "\\").split("\\"):
        stem = component.split(".", 1)[0].upper()
        if (":" in component or component.endswith((" ", "."))
                or stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                or (len(stem) == 4 and stem[:3] in {"COM", "LPT"}
                    and stem[3] in "123456789¹²³")):
            raise ValueError("Upload device/stream paths are not supported")

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    file_type = kernel.GetFileType
    file_type.argtypes, file_type.restype = (wintypes.HANDLE,), wintypes.DWORD
    query = kernel.GetFileInformationByHandleEx
    query.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    query.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes, close.restype = (wintypes.HANDLE,), wintypes.BOOL

    class AttributeTag(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]

    # GENERIC_READ, SHARE_READ|WRITE|DELETE, NULL security (not inheritable),
    # OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT. No directory/backup privilege.
    handle = create(path, 0x80000000, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if file_type(handle) != 1:  # FILE_TYPE_DISK only, never pipe/character device
            raise ValueError("Upload handle is not a disk file")
        attributes = AttributeTag()
        if not query(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)):
            raise ctypes.WinError(ctypes.get_last_error())
        # FileAttributeTagInfo: reject ALL reparse tags, not just symlinks, and dirs.
        if attributes.attributes & (0x400 | 0x10):
            raise ValueError("Upload reparse points/directories are not supported")
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
    except BaseException:
        close(handle)  # No CRT fd owns the handle on failure.
        raise
    # Success transfers handle ownership to the fd: ONLY os.close(fd) may close it.
    return fd
