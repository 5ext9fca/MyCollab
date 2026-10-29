"""模型进程的创建入口；Windows 进程执行前即处于 Job 保护中。"""
import os
import subprocess


def spawn(command, **options):
    if os.name != 'nt':
        return subprocess.Popen(command, **options)
    from .windows_job import ProcessJob, protect_runner_tree
    protect_runner_tree()
    job = ProcessJob()
    process = None
    try:
        options['creationflags'] = options.get('creationflags', 0) | 0x00000004 | 0x08000000
        process = subprocess.Popen(command, **options)
        process._mycollab_job = job
        job.assign_and_resume(process.pid)
        return process
    except BaseException:
        try:
            job.close()
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
        raise


def version_check(executable):
    if os.name != 'nt':
        return subprocess.run([executable, '--version'], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    process = spawn([executable, '--version'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        stdout, _ = process.communicate(timeout=15)
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, '')
    finally:
        process._mycollab_job.close()
        process.wait()
        if process.stdout:
            process.stdout.close()


def diagnose_executable(executable):
    """只返回固定失败分类，不暴露路径、异常文本或模型输出。"""
    try:
        version = version_check(executable)
    except FileNotFoundError:
        return {'opencode': 'unavailable', 'opencode_error': 'not_found'}
    except PermissionError:
        return {'opencode': 'unavailable', 'opencode_error': 'permission_denied'}
    except subprocess.TimeoutExpired:
        return {'opencode': 'unavailable', 'opencode_error': 'timeout'}
    except UnicodeError:
        return {'opencode': 'unavailable', 'opencode_error': 'invalid_output'}
    except OSError:
        return {'opencode': 'unavailable', 'opencode_error': 'spawn_failed'}
    if version.returncode:
        return {'opencode': 'unavailable', 'opencode_error': 'nonzero_exit'}
    if version.stdout.strip() != 'opencode v2.1.3':
        return {'opencode': 'incompatible', 'opencode_error': 'version_mismatch'}
    return {'opencode': 'ok'}
