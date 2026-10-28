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
        return subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=15)
    process = spawn([executable, '--version'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        stdout, _ = process.communicate(timeout=15)
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, '')
    finally:
        process._mycollab_job.close()
        process.wait()
        if process.stdout:
            process.stdout.close()
