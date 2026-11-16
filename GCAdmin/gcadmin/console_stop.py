"""Inject Ctrl+Z / Enter into one Windows console; never terminates a process."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import os
import sys


def send(pid):
    if os.name != 'nt':
        raise RuntimeError('Encerramento por consola só está disponível no Windows.')

    class Key(C.Structure):
        _fields_ = [('down', W.BOOL), ('repeat', W.WORD), ('vk', W.WORD),
                    ('scan', W.WORD), ('character', W.WCHAR), ('control', W.DWORD)]

    class Union(C.Union):
        _fields_ = [('key', Key), ('padding', C.c_byte * 16)]

    class Record(C.Structure):
        _fields_ = [('type', W.WORD), ('event', Union)]

    assert C.sizeof(Record) == 20
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.AttachConsole.argtypes = [W.DWORD]
    kernel.AttachConsole.restype = W.BOOL
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p,
                                   W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.WriteConsoleInputW.argtypes = [W.HANDLE, C.POINTER(Record), W.DWORD, C.POINTER(W.DWORD)]
    kernel.WriteConsoleInputW.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.FreeConsole()
    handle = None
    try:
        if not kernel.AttachConsole(pid):
            raise C.WinError(C.get_last_error())
        handle = kernel.CreateFileW('CONIN$', 0xC0000000, 3, None, 3, 0, None)
        if handle == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        records = (Record * 4)()
        for i, (vk, char, down, control) in enumerate([
            (0x5A, '\x1a', True, 8), (0x5A, '\x1a', False, 8),
            (0x0D, '\r', True, 0), (0x0D, '\r', False, 0)
        ]):
            records[i].type = 1
            records[i].event.key = Key(down, 1, vk, 0, char, control)
        written = W.DWORD()
        if not kernel.WriteConsoleInputW(handle, records, 4, C.byref(written)) or written.value != 4:
            raise C.WinError(C.get_last_error())
    finally:
        if handle is not None and handle != C.c_void_p(-1).value:
            kernel.CloseHandle(handle)
        kernel.FreeConsole()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    args = parser.parse_args()
    try:
        send(args.pid)
    except Exception as exc:
        # Console may have been detached; exit status still reliably reaches caller.
        try:
            print(str(exc), file=sys.stderr)
        except OSError:
            pass
        sys.exit(1)
