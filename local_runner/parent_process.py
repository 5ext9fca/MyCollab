"""监测桌面宿主退出；Windows 不可使用 os.kill(pid, 0) 探测。"""
import os


class ParentProcess:
    def __init__(self, pid):
        self.pid = pid
        self.handle = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype = wintypes.DWORD
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
            self.handle = self.kernel.OpenProcess(0x00100000, False, pid)
            if not self.handle:
                error = ctypes.get_last_error()
                if error != 87:
                    raise ctypes.WinError(error)

    def alive(self):
        if os.name == 'nt':
            if not self.handle:
                return False
            result = self.kernel.WaitForSingleObject(self.handle, 0)
            if result == 0:
                return False
            if result == 258:
                return True
            raise OSError('无法监测桌面宿主。')
        try:
            os.kill(self.pid, 0)
            return True
        except ProcessLookupError:
            return False

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
