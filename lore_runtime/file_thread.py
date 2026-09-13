"""Run only F signal-window operations on the existing Runtime main loop."""
import asyncio
import copy
import math
import threading
from concurrent.futures import Future, TimeoutError

from lore_files import FileStore
from lore_files.errors import FileError, require


class RuntimeFiles(FileStore):
    def __init__(self, *args, control, delegate_timeout=30, **kwargs):
        require(callable(getattr(getattr(control, "_lock", None), "_is_owned", None)),
                "UNSUPPORTED", "original R lock ownership must be observable")
        require(type(delegate_timeout) in (int, float) and math.isfinite(delegate_timeout)
                and 0 < delegate_timeout <= 30, "UNSUPPORTED", "finite F delegation bound required")
        self._runtime_control = control
        self._delegate_timeout = delegate_timeout
        self._runtime_loop = None
        super().__init__(*args, **kwargs)

    def bind_loop(self, loop):
        require(threading.current_thread() is threading.main_thread(),
                "UNSUPPORTED", "F signal loop must belong to the main thread")
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        require(current is loop and loop is not None and loop.is_running() and not loop.is_closed(),
                "UNSUPPORTED", "bind the actual running main loop")
        require(self._runtime_loop is None or self._runtime_loop is loop,
                "UNSUPPORTED", "original F loop cannot be replaced")
        self._runtime_loop = loop

    def _on_main(self, method, args, kwargs, *, callbacks):
        if threading.current_thread() is threading.main_thread():
            return method(*args, **kwargs)
        require(not callbacks or not self._runtime_control._lock._is_owned(),
                "UNSUPPORTED", "worker holding R lock cannot delegate F authority callbacks")
        loop = self._runtime_loop
        require(loop is not None and loop.is_running() and not loop.is_closed(),
                "UNSUPPORTED", "original F main loop is unavailable")
        args, kwargs = copy.deepcopy(args), copy.deepcopy(kwargs)
        pending = Future()

        def invoke():
            # A cancelled queued call must not become a late new F operation.
            if not pending.set_running_or_notify_cancel():
                return
            try:
                value = method(*args, **kwargs)
            except BaseException as exc:
                pending.set_exception(exc)
            else:
                pending.set_result(value)

        try:
            loop.call_soon_threadsafe(invoke)
        except RuntimeError as exc:
            pending.cancel()
            raise FileError("UNSUPPORTED", "original F main loop is unavailable") from exc
        try:
            return pending.result(timeout=self._delegate_timeout)
        except TimeoutError as exc:
            # If already running, cancellation is false: F completes under its
            # original request ID. Only F's existing record can establish outcome.
            pending.cancel()
            raise FileError("PUBLICATION_UNKNOWN", "original F operation did not finish within the caller bound") from exc

    def capture(self, *args, **kwargs):
        return self._on_main(super().capture, args, kwargs, callbacks=True)

    def install(self, *args, **kwargs):
        return self._on_main(super().install, args, kwargs, callbacks=True)

    def query_install(self, *args, **kwargs):
        # Installer.query reads original F records and windows only; no R or
        # authorization callback. R confirmation/release may already own R._lock.
        return self._on_main(super().query_install, args, kwargs, callbacks=False)
