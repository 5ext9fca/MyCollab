"""先挂起创建、加入 Job，再恢复线程；关闭 Job 终止整个模型进程树。"""
import ctypes
from ctypes import wintypes


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', wintypes.DWORD), ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t),
                ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', ctypes.c_uint64 * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


class ThreadEntry(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('thread_id', wintypes.DWORD),
                ('process_id', wintypes.DWORD), ('base_priority', wintypes.LONG),
                ('delta_priority', wintypes.LONG), ('flags', wintypes.DWORD)]


class ProcessJob:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.handle = None
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
            'CreateToolhelp32Snapshot': ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            'Thread32First': ([wintypes.HANDLE, ctypes.POINTER(ThreadEntry)], wintypes.BOOL),
            'Thread32Next': ([wintypes.HANDLE, ctypes.POINTER(ThreadEntry)], wintypes.BOOL),
            'OpenThread': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'ResumeThread': ([wintypes.HANDLE], wintypes.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE，不允许 breakaway。
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def assign(self, pid):
        process = self.kernel.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(process)
    def assign_and_resume(self, pid):
        self.assign(pid)
        # Popen 关闭了主线程原始句柄；通过受挂起保护的 PID 重新取得主线程。
        snapshot = self.kernel.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = self.kernel.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.process_id == pid:
                    thread = self.kernel.OpenThread(0x0002, False, entry.thread_id)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self.kernel.ResumeThread(thread) == 0xffffffff:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        self.kernel.CloseHandle(thread)
                entry.size = ctypes.sizeof(entry)
                found = self.kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError('无法恢复模型进程主线程。')
        finally:
            self.kernel.CloseHandle(snapshot)

    def close(self):
        if self.handle:
            if not self.kernel.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


_runner_job = None


def protect_runner_tree():
    global _runner_job
    if _runner_job is not None:
        return
    import os
    job = ProcessJob()
    try:
        job.assign(os.getpid())
    except BaseException:
        job.close()
        raise
    # 不在正常 Python 清理时关闭自身 Job；交由 OS 在进程退出时释放。
    # 模型在加入独立 Job 前的挂起窗口，也已继承这个外层 Job。
    _runner_job = job
