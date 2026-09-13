"""One shared nats-py read connection for synchronous R reference checks."""
import asyncio
import re
import threading
import nats


class JetStreamReader:
    def __init__(self, url, *, timeout=2.0):
        if not isinstance(url, str) or not url or not 0 < timeout <= 5:
            raise ValueError('trusted NATS endpoint and bounded timeout required')
        self.url, self.timeout = url, timeout
        self.loop = self.thread = self.nc = self.js = None
        self.errors = []

    async def _error(self, error):
        self.errors.append(type(error).__name__)
        del self.errors[:-16]

    async def _connect(self):
        self.nc = await nats.connect(servers=[self.url], allow_reconnect=False,
                                     connect_timeout=self.timeout, error_cb=self._error)
        self.js = self.nc.jetstream(timeout=self.timeout)

    def _call(self, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(self.timeout + 1)
        except BaseException:
            future.cancel()
            raise

    def open(self):
        if self.thread is not None:
            raise RuntimeError('reader lifecycle already started')
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever,
                                       name='lore-original-nats-reader', daemon=False)
        self.thread.start()
        try:
            self._call(self._connect())
        except BaseException:
            self.close()
            raise
        return self

    def read(self, stream, sequence):
        if self.js is None or not self.thread.is_alive():
            raise RuntimeError('original NATS reader is unavailable')
        if type(stream) is not str or not re.fullmatch(r'[A-Za-z0-9_-]+', stream) or type(sequence) is not int or sequence < 1:
            raise ValueError('exact original stream and positive sequence required')
        return self._call(self.js.get_msg(stream, seq=sequence))

    async def _close(self):
        if self.nc is not None:
            await self.nc.close()
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def close(self):
        if self.thread is None or not self.thread.is_alive():
            return
        try:
            self._call(self._close())
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(self.timeout + 1)
            if self.thread.is_alive():
                raise RuntimeError('owned original-reader thread did not close')
            self.loop.close()
            self.nc = self.js = None
