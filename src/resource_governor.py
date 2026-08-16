from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Iterator, Literal


ComputeProfile = Literal["responsive", "balanced", "performance"]
ResourceName = Literal["gpu", "cpu", "ffmpeg"]


def state_root() -> Path:
    configured = str(os.environ.get("VIEWLEDGE_STATE_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        return (Path(local_app_data) / "Viewledge" / "state").resolve()
    return (Path.cwd() / ".local").resolve()


def lock_path(resource: ResourceName) -> Path:
    return state_root() / "runtime_locks" / f"{resource}.lock"


def cpu_thread_limit(profile: str = "responsive", configured: int = 0) -> int:
    if configured > 0:
        return max(1, min(int(configured), 64))
    logical = max(1, int(os.cpu_count() or 1))
    normalized = str(profile or "responsive").strip().lower()
    if normalized == "performance":
        return max(1, min(8, logical - 1))
    if normalized == "balanced":
        return max(1, min(6, logical // 2))
    return max(1, min(4, logical // 3 or 1))


def apply_cpu_environment(profile: str = "responsive", configured: int = 0) -> int:
    threads = cpu_thread_limit(profile, configured)
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = str(threads)
    return threads


def set_process_below_normal() -> None:
    if os.name != "nt":
        try:
            os.nice(5)
        except (AttributeError, OSError):
            pass
        return
    try:
        import ctypes

        handle = ctypes.windll.kernel32.GetCurrentProcess()
        # BELOW_NORMAL_PRIORITY_CLASS from WinBase.h.
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
    except (AttributeError, OSError):
        pass


@contextlib.contextmanager
def resource_guard(
    resource: ResourceName,
    *,
    timeout_seconds: float = 300.0,
    profile: str = "responsive",
    configured_threads: int = 0,
) -> Iterator[None]:
    """Cross-process single-slot guard for heavy local resources."""
    path = lock_path(resource)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Restricted test runners may not allow LOCALAPPDATA writes; keep the
        # guard functional with the repository-local state fallback.
        path = (Path(__file__).resolve().parents[1] / ".local" / "runtime_locks" / f"{resource}.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        acquired = False
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"等待 {resource} 资源超时。")
                time.sleep(0.1)
        if resource in {"cpu", "ffmpeg"}:
            apply_cpu_environment(profile, configured_threads)
            set_process_below_normal()
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
