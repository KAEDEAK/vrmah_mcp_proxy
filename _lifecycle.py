"""Process lifecycle watchdogs for vrmah_mcp_proxy.

Same problem as mrelay-mcp: long-lived MCP hosts (Codex Desktop's
``codex.exe app-server`` in particular) sometimes spawn a fresh
``vrmah_mcp_proxy`` subprocess without killing the previous one. The
orphan generations sit idle, hold their stdin pipes open (so the
proxy's natural EOF exit never fires), and accumulate over hours.

The first vrmah lifecycle used an unconditional hard idle timeout to
make old Codex subprocesses disappear. That fixed accumulation, but it
also killed the *current* stdio transport while Codex Desktop still kept
the tool handle. The next tool call then failed with ``Transport closed``
instead of spawning a replacement process.

This version keeps the current transport alive by default and moves
cleanup to startup: a new proxy generation registers itself and
supersedes older running entries that share the same client/config key.
The hard idle timeout still exists as an explicit opt-in escape hatch.

Three watchdogs are installed by ``startup()`` as daemon threads:

1. ``_idle_loop``  : optional hard idle timeout
                     (``VRMAH_PROC_HARD_IDLE_SEC``). Resets each time
                     ``mark_request_end()`` brings the in-flight counter
                     back to zero. Default 0 (= disabled).
2. registry        : tracks live generations and terminates older
                     matching entries at startup
                     (``VRMAH_SUPERSEDE_OLDER``).
3. ``_parent_loop``: psutil-based polling of the original parent PID.
                     Detects parent death within ``VRMAH_PARENT_WATCH_SEC``
                     (default 30s). Also catches the PID-reuse case
                     (= same PID but different ``create_time``).
4. ``_native_parent_loop``: blocks on an OS primitive
                     (``WaitForSingleObject`` on Windows,
                     ``pidfd_open`` + ``select`` on Linux) so parent
                     death is detected within ~1s without polling.
                     Skipped on macOS / older platforms.

All exits route through ``shutdown(reason)`` which returns True for the
winning caller — watchdogs gate their ``os._exit(0)`` on this return
so a real KeyboardInterrupt / exception in ``main()`` is not
overwritten with a misleading ``hard_idle_timeout`` in a race.

Environment knobs:

- ``VRMAH_PROC_HARD_IDLE_SEC`` : default 0; set >0 to enable.
- ``VRMAH_PARENT_WATCH_SEC``   : default 30;  set 0 to disable.
- ``VRMAH_NATIVE_PARENT_WAIT`` : default 1;   set 0 to disable.
- ``VRMAH_SUPERSEDE_OLDER``    : default 1;   set 0 to disable.
- ``VRMAH_SUPERSEDE_GRACE_SEC``: default 5.0.
- ``VRMAH_INSTANCE_REGISTRY``  : optional registry path override.
- ``VRMAH_LIFECYCLE_LOG``      : default 1;   set 0 to silence logs.
- ``VRMAH_PROC_IDLE_POLL_SEC`` : optional override of the idle loop
                                  tick (auto-derived as TTL/10 otherwise).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

if os.name == "nt":  # pragma: no cover - Windows-only in production
    import msvcrt
else:  # pragma: no cover - POSIX only
    import fcntl
    import select


_REGISTRY_VERSION = 1
_DEFAULT_REGISTRY_PATH = Path(__file__).with_name("instance_registry.json")


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_flag(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _derive_poll_interval(idle_ttl_sec: int, env_override: Optional[str]) -> float:
    if env_override is not None and env_override != "":
        try:
            v = float(env_override)
            if v > 0:
                return v
        except ValueError:
            pass
    if idle_ttl_sec <= 0:
        return 30.0
    return max(0.5, min(30.0, idle_ttl_sec / 10.0))


def _safe_create_time(pid: int) -> Optional[float]:
    if psutil is None:
        return None
    try:
        return psutil.Process(pid).create_time()
    except Exception:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _registry_path() -> Path:
    raw = os.environ.get("VRMAH_INSTANCE_REGISTRY")
    if raw:
        return Path(raw)
    return _DEFAULT_REGISTRY_PATH


def _default_registry_doc() -> dict:
    return {"version": _REGISTRY_VERSION, "instances": []}


def _read_registry_unlocked(path: Path) -> dict:
    if not path.exists():
        return _default_registry_doc()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_registry_doc()
    if not isinstance(raw, dict):
        return _default_registry_doc()
    instances = raw.get("instances")
    if not isinstance(instances, list):
        instances = []
    return {"version": _REGISTRY_VERSION, "instances": instances}


def _write_registry_unlocked(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    payload = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
    try:
        with tmp_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


@contextmanager
def _registry_lock(path: Path):
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"0")
            fh.flush()
        fh.seek(0)
        if os.name == "nt":
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:  # pragma: no cover - POSIX only
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fh.seek(0)
            if os.name == "nt":
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - POSIX only
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _entry_matches_process(entry: dict, proc: Any) -> bool:
    expected = _as_float(entry.get("pid_create_time"))
    if expected is None:
        return True
    try:
        actual = proc.create_time()
    except Exception:
        return True
    return actual == expected


def _instance_is_live(entry: dict) -> bool:
    pid = _as_int(entry.get("pid"))
    if pid is None or pid <= 0:
        return False
    if psutil is None:
        return True
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        try:
            if proc.status() == getattr(psutil, "STATUS_ZOMBIE", "zombie"):
                return False
        except Exception:
            pass
        return _entry_matches_process(entry, proc)
    except psutil.NoSuchProcess:
        return False
    except Exception:
        return True


def _prune_dead_instances(instances: List[Any]) -> List[dict]:
    live: List[dict] = []
    for entry in instances:
        if not isinstance(entry, dict):
            continue
        if _instance_is_live(entry):
            live.append(entry)
    return live


def _sorted_instances(instances: List[dict]) -> List[dict]:
    return sorted(
        instances,
        key=lambda item: (
            _as_float(item.get("started_ts")) or 0.0,
            _as_int(item.get("pid")) or 0,
        ),
    )


def _mutate_registry(mutator: Callable[[List[dict]], Tuple[List[dict], Any]]) -> Any:
    path = _registry_path()
    with _registry_lock(path):
        doc = _read_registry_unlocked(path)
        instances = _prune_dead_instances(doc.get("instances", []))
        instances, result = mutator(instances)
        _write_registry_unlocked(
            path,
            {"version": _REGISTRY_VERSION, "instances": instances},
        )
        return result


def _detect_host_kind(initial_ppid: int) -> str:
    if psutil is None:
        return "unknown"
    pid: Optional[int] = initial_ppid
    for _ in range(6):
        if pid is None or pid <= 0:
            break
        try:
            proc = psutil.Process(pid)
            parts = [proc.name()]
            try:
                parts.extend(proc.cmdline())
            except Exception:
                pass
            blob = " ".join(str(part).lower() for part in parts)
            if "codex" in blob:
                return "codex"
            if "claude" in blob:
                return "claude"
            if "code.exe" in blob or "visual studio code" in blob or "vscode" in blob:
                return "vscode"
            pid = proc.ppid()
        except Exception:
            break
    return "unknown"


def _config_arg_from_argv() -> str:
    argv = list(sys.argv)
    for index, item in enumerate(argv):
        if item == "--config" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--config="):
            return item.split("=", 1)[1]
    return os.environ.get("VRM_MCP_CONFIG", "config.json")


# ---------------------------------------------------------------------------
# Native parent waiter (no-polling parent-death detection)
# ---------------------------------------------------------------------------


class _NativeParentWaiter:
    """Block on an OS primitive until ``ppid`` terminates.

    Windows: WaitForSingleObject on OpenProcess(PROCESS_SYNCHRONIZE).
    Linux:   pidfd_open + select.select on the fd.
    Other:   is_supported() returns False and caller falls back to
             the psutil polling watchdog.

    Both implementations tick on a short interval (1s) so close() /
    stop_event can interrupt the daemon thread without leaving a real
    kernel wait pinned forever.
    """

    def __init__(self, ppid: int) -> None:
        self._ppid = ppid

    @staticmethod
    def is_supported() -> bool:
        if os.name == "nt":
            return True
        return hasattr(os, "pidfd_open")

    def wait(self, stop_event: threading.Event) -> bool:
        if os.name == "nt":
            return self._wait_windows(stop_event)
        if hasattr(os, "pidfd_open"):
            return self._wait_linux(stop_event)
        return False

    def _wait_windows(self, stop_event):  # pragma: no cover - Windows-only
        import ctypes
        from ctypes import wintypes

        PROCESS_SYNCHRONIZE = 0x00100000
        WAIT_OBJECT_0 = 0x00000000
        WAIT_TIMEOUT = 0x00000102

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(PROCESS_SYNCHRONIZE, False, self._ppid)
        if not handle:
            return False
        try:
            while not stop_event.is_set():
                rc = kernel32.WaitForSingleObject(handle, 1000)
                if rc == WAIT_OBJECT_0:
                    return True
                if rc == WAIT_TIMEOUT:
                    continue
                return False
            return False
        finally:
            kernel32.CloseHandle(handle)

    def _wait_linux(self, stop_event):  # pragma: no cover - Linux-only
        try:
            pidfd = os.pidfd_open(self._ppid)
        except (OSError, AttributeError):
            return False
        try:
            while not stop_event.is_set():
                try:
                    ready, _, _ = select.select([pidfd], [], [], 1.0)
                except OSError:
                    return True
                if ready:
                    return True
            return False
        finally:
            try:
                os.close(pidfd)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Lifecycle context
# ---------------------------------------------------------------------------


class _NoOpContext:
    """Default context installed at import time so callers can use the
    module-level ``mark_request_start/end`` helpers even before
    ``startup()`` has run (e.g. during unit tests)."""

    def mark_request_start(self) -> None:
        return None

    def mark_request_end(self) -> None:
        return None

    def shutdown(self, reason: str, **extra: Any) -> bool:
        return False


class LifecycleContext:
    def __init__(self, config_file: str = "", base_url: str = "") -> None:
        self._hard_idle_sec = _env_int("VRMAH_PROC_HARD_IDLE_SEC", 0)
        self._parent_watch_sec = _env_int("VRMAH_PARENT_WATCH_SEC", 30)
        self._native_parent_wait_enabled = bool(
            _env_flag("VRMAH_NATIVE_PARENT_WAIT", 1)
        )
        self._supersede_enabled = bool(_env_flag("VRMAH_SUPERSEDE_OLDER", 1))
        self._supersede_grace_sec = _env_float("VRMAH_SUPERSEDE_GRACE_SEC", 5.0)
        self._lifecycle_log_enabled = bool(_env_flag("VRMAH_LIFECYCLE_LOG", 1))
        self._poll_interval = _derive_poll_interval(
            self._hard_idle_sec,
            os.environ.get("VRMAH_PROC_IDLE_POLL_SEC"),
        )

        self._lock = threading.Lock()
        self._in_flight = 0
        self._last_idle_at = time.monotonic()
        self._shutdown_emitted = False
        self._stop_event = threading.Event()
        self._idle_thread: Optional[threading.Thread] = None
        self._parent_thread: Optional[threading.Thread] = None
        self._native_parent_thread: Optional[threading.Thread] = None

        self._pid = os.getpid()
        self._initial_ppid = os.getppid()
        self._pid_create_time = _safe_create_time(self._pid)
        self._started_dt = _utc_now()
        self._started_ts = self._started_dt.timestamp()
        self._started_at = _isoformat_utc(self._started_dt)
        self._config_file = config_file or _config_arg_from_argv()
        self._base_url = base_url or ""
        self._script_file = str(Path(sys.argv[0]).resolve()) if sys.argv else ""
        self._host_kind = _detect_host_kind(self._initial_ppid)
        self._cwd = os.getcwd()
        self._initial_ppid_create_time: Optional[float] = None
        if psutil is not None and self._parent_watch_sec > 0:
            self._initial_ppid_create_time = _safe_create_time(self._initial_ppid)

    # ----- public API -----

    def mark_request_start(self) -> None:
        with self._lock:
            self._in_flight += 1

    def mark_request_end(self) -> None:
        with self._lock:
            if self._in_flight > 0:
                self._in_flight -= 1
            if self._in_flight == 0:
                # Restart the idle clock the moment we drop back to zero.
                self._last_idle_at = time.monotonic()

    def shutdown(self, reason: str, **extra: Any) -> bool:
        with self._lock:
            if self._shutdown_emitted:
                return False
            self._shutdown_emitted = True
        self._mark_instance_stopped(reason)
        if self._lifecycle_log_enabled:
            parts = [
                "event=shutdown",
                f"pid={os.getpid()}",
                f"reason={reason}",
            ]
            for k, v in extra.items():
                parts.append(f"{k}={v}")
            sys.stderr.write("[vrmah-proxy lifecycle] " + " ".join(parts) + "\n")
            try:
                sys.stderr.flush()
            except Exception:
                pass
        return True

    def close(self) -> None:
        """Stop watchdog threads. Idempotent. Test-only."""
        self._stop_event.set()
        for t in (
            self._idle_thread,
            self._parent_thread,
            self._native_parent_thread,
        ):
            if t is not None and t.is_alive():
                t.join(timeout=2.0)

    # ----- startup -----

    def register_instance(self) -> None:
        superseded_pids = _mutate_registry(self._register_instance_mutation)
        if self._supersede_enabled and superseded_pids:
            self._terminate_superseded(superseded_pids)

    def _emit_startup(self) -> None:
        if not self._lifecycle_log_enabled:
            return
        native_wait = int(
            self._native_parent_wait_enabled
            and _NativeParentWaiter.is_supported()
        )
        sys.stderr.write(
            "[vrmah-proxy lifecycle] "
            f"event=startup pid={self._pid} ppid={self._initial_ppid} "
            f"start={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
            f"host_kind={self._host_kind} "
            f"script_file={self._script_file} "
            f"config_file={self._config_file} "
            f"base_url={self._base_url} "
            f"hard_idle_sec={self._hard_idle_sec} "
            f"parent_watch_sec={self._parent_watch_sec} "
            f"native_parent_wait={native_wait} "
            f"supersede_older={int(self._supersede_enabled)}\n"
        )
        try:
            sys.stderr.flush()
        except Exception:
            pass

    # ----- registry -----

    def _identity(self) -> Tuple[str, str, str, str, str]:
        return (
            self._host_kind,
            self._script_file,
            self._config_file,
            self._base_url,
            self._cwd,
        )

    def _instance_record(self) -> dict:
        return {
            "pid": self._pid,
            "ppid": self._initial_ppid,
            "pid_create_time": self._pid_create_time,
            "started_at": self._started_at,
            "started_ts": self._started_ts,
            "status": "running",
            "ended_at": None,
            "shutdown_reason": None,
            "host_kind": self._host_kind,
            "script_file": self._script_file,
            "config_file": self._config_file,
            "base_url": self._base_url,
            "cwd": self._cwd,
        }

    def _same_process(self, entry: dict) -> bool:
        pid = _as_int(entry.get("pid"))
        if pid != self._pid:
            return False
        expected = _as_float(entry.get("pid_create_time"))
        if expected is None or self._pid_create_time is None:
            return True
        return expected == self._pid_create_time

    def _entry_identity(self, entry: dict) -> Tuple[str, str, str, str, str]:
        return (
            str(entry.get("host_kind", "")),
            str(entry.get("script_file", "")),
            str(entry.get("config_file", "")),
            str(entry.get("base_url", "")),
            str(entry.get("cwd", "")),
        )

    def _register_instance_mutation(self, instances: List[dict]) -> Tuple[List[dict], List[int]]:
        ended_at = _isoformat_utc(_utc_now())
        kept: List[dict] = []
        superseded: List[int] = []
        for entry in instances:
            if self._same_process(entry):
                continue
            if self._is_supersession_candidate(entry):
                pid = _as_int(entry.get("pid"))
                if pid is not None and pid > 0:
                    superseded.append(pid)
                new_entry = dict(entry)
                new_entry["status"] = "stopped"
                new_entry["ended_at"] = ended_at
                new_entry["shutdown_reason"] = f"superseded_by_pid={self._pid}"
                kept.append(new_entry)
                continue
            kept.append(entry)
        kept.append(self._instance_record())
        return _sorted_instances(kept), superseded

    def _mark_instance_stopped(self, reason: str) -> None:
        ended_at = _isoformat_utc(_utc_now())

        def mutate(instances: List[dict]) -> Tuple[List[dict], None]:
            updated: List[dict] = []
            found = False
            for entry in instances:
                if self._same_process(entry):
                    new_entry = dict(entry)
                    new_entry["status"] = "stopped"
                    new_entry["ended_at"] = ended_at
                    new_entry["shutdown_reason"] = reason
                    updated.append(new_entry)
                    found = True
                else:
                    updated.append(entry)
            if not found:
                new_entry = self._instance_record()
                new_entry["status"] = "stopped"
                new_entry["ended_at"] = ended_at
                new_entry["shutdown_reason"] = reason
                updated.append(new_entry)
            return _sorted_instances(updated), None

        _mutate_registry(mutate)

    def _is_supersession_candidate(self, entry: dict) -> bool:
        if entry.get("status") != "running":
            return False
        pid = _as_int(entry.get("pid"))
        if pid == self._pid:
            return False
        if self._entry_identity(entry) != self._identity():
            return False
        started_ts = _as_float(entry.get("started_ts"))
        if started_ts is not None:
            age = self._started_ts - started_ts
            if age < self._supersede_grace_sec:
                return False
        return True

    def _terminate_superseded(self, pids: List[int]) -> None:
        if psutil is None or not pids:
            return
        for pid in pids:
            try:
                proc = psutil.Process(pid)
            except psutil.NoSuchProcess:
                continue
            except Exception:
                continue
            if self._lifecycle_log_enabled:
                sys.stderr.write(
                    "[vrmah-proxy lifecycle] "
                    f"event=supersede target_pid={pid} my_pid={self._pid} "
                    f"host_kind={self._host_kind} config_file={self._config_file}\n"
                )
                try:
                    sys.stderr.flush()
                except Exception:
                    pass
            try:
                proc.terminate()
            except Exception:
                continue
            try:
                proc.wait(timeout=3.0)
            except psutil.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
            except Exception:
                pass

    def start_watchdogs(self) -> None:
        if self._hard_idle_sec > 0:
            t = threading.Thread(
                target=self._idle_loop,
                daemon=True,
                name="vrmah-idle-watchdog",
            )
            t.start()
            self._idle_thread = t
        if self._parent_watch_sec > 0 and self._initial_ppid_create_time is not None:
            t = threading.Thread(
                target=self._parent_loop,
                daemon=True,
                name="vrmah-parent-watchdog",
            )
            t.start()
            self._parent_thread = t
        if self._native_parent_wait_enabled and _NativeParentWaiter.is_supported():
            t = threading.Thread(
                target=self._native_parent_loop,
                daemon=True,
                name="vrmah-parent-wait-native",
            )
            t.start()
            self._native_parent_thread = t

    # ----- watchdog loops -----

    def _idle_loop(self) -> None:
        if self._hard_idle_sec <= 0:
            return
        while not self._stop_event.is_set():
            if self._stop_event.wait(self._poll_interval):
                return
            with self._lock:
                in_flight = self._in_flight
                last_idle = self._last_idle_at
            if in_flight > 0:
                continue
            elapsed = time.monotonic() - last_idle
            if elapsed < self._hard_idle_sec:
                continue
            if self.shutdown("hard_idle_timeout", elapsed_sec=int(elapsed)):
                os._exit(0)
            return

    def _parent_loop(self) -> None:
        if self._parent_watch_sec <= 0 or psutil is None:
            return
        while not self._stop_event.is_set():
            if self._stop_event.wait(self._parent_watch_sec):
                return
            try:
                p = psutil.Process(self._initial_ppid)
                running = p.is_running()
                status = None
                try:
                    status = p.status()
                except Exception:
                    pass
                if not running or status == getattr(psutil, "STATUS_ZOMBIE", "zombie"):
                    if self.shutdown("parent_gone", ppid=self._initial_ppid):
                        os._exit(0)
                    return
                if self._initial_ppid_create_time is not None and (
                    p.create_time() != self._initial_ppid_create_time
                ):
                    if self.shutdown(
                        "parent_gone",
                        ppid=self._initial_ppid,
                        detail="ppid_reused",
                    ):
                        os._exit(0)
                    return
            except psutil.NoSuchProcess:
                if self.shutdown("parent_gone", ppid=self._initial_ppid):
                    os._exit(0)
                return
            except Exception:
                # Transient psutil errors (= access denied flicker on
                # Windows) should not cause exit.
                pass

    def _native_parent_loop(self) -> None:
        waiter = _NativeParentWaiter(self._initial_ppid)
        died = waiter.wait(self._stop_event)
        if not died:
            return
        if self.shutdown(
            "parent_gone",
            ppid=self._initial_ppid,
            detail="native_wait",
        ):
            os._exit(0)


# ---------------------------------------------------------------------------
# Module-level dispatch
# ---------------------------------------------------------------------------


_ctx: Any = _NoOpContext()


def startup(config_file: str = "", base_url: str = "") -> LifecycleContext:
    """Install a real lifecycle context, log startup, start watchdogs."""
    global _ctx
    ctx = LifecycleContext(config_file=config_file, base_url=base_url)
    _ctx = ctx
    ctx.register_instance()
    ctx._emit_startup()
    ctx.start_watchdogs()
    return ctx


def mark_request_start() -> None:
    _ctx.mark_request_start()


def mark_request_end() -> None:
    _ctx.mark_request_end()


def shutdown(reason: str, **extra: Any) -> bool:
    return _ctx.shutdown(reason, **extra)


def reset_to_noop_for_test() -> None:
    """Stop watchdog threads and restore the NoOp default.

    Tests-only. Production never calls this.
    """
    global _ctx
    if isinstance(_ctx, LifecycleContext):
        _ctx.close()
    _ctx = _NoOpContext()
