"""按平台建立私有状态目录与随进程释放的独占锁。"""
from contextlib import contextmanager
import errno
import os
from pathlib import Path


def private_directory(path):
    path = Path(path)
    if path.is_symlink() or path.is_junction():
        raise ValueError('私有状态目录不能是链接。')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'nt':
        from .windows_security import restrict_directory
        restrict_directory(path)
    else:
        path.chmod(0o700)
    return path


def private_file_descriptor(fd):
    # Windows 文件继承已保护父目录的 DACL，chmod 不是访问控制替代品。
    if os.name == 'posix':
        os.fchmod(fd, 0o600)


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Runner 锁文件不能是链接。')
    with path.open('a+b') as stream:
        private_file_descriptor(stream.fileno())
        if os.name == 'nt':
            import msvcrt
            # 锁从当前游标开始；始终锁第 0 字节，空文件也可锁定。
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise ValueError('该设备的 Runner 已在运行。') from exc
                raise
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('该设备的 Runner 已在运行。') from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
