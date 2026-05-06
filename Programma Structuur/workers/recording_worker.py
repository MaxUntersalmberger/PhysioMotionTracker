from __future__ import annotations

import logging
import queue
import threading

from PySide6.QtCore import QThread, Signal

from capture.backend import CaptureBatch
from session.recorder import SessionRecorder, SessionRecordingStats


LOGGER = logging.getLogger(__name__)


class RecordingWorker(QThread):
    stats_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(self, recorder: SessionRecorder, queue_size: int = 240) -> None:
        super().__init__()
        self._recorder = recorder
        self._queue: queue.Queue[CaptureBatch] = queue.Queue(maxsize=max(1, int(queue_size)))
        self._stop_event = threading.Event()
        self._dropped_queue_batches = 0
        self._latest_stats: SessionRecordingStats | None = None

    @property
    def latest_stats(self) -> SessionRecordingStats | None:
        return self._latest_stats

    def stop(self) -> None:
        self._stop_event.set()

    def submit_batch(self, batch: CaptureBatch) -> None:
        if not batch.frames:
            return
        try:
            self._queue.put_nowait(batch)
        except queue.Full:
            self._dropped_queue_batches += 1
            self.state_changed.emit("recording_queue_full")

    def run(self) -> None:
        self.state_changed.emit("recording_starting")
        try:
            self._latest_stats = self._recorder.start()
            self.stats_ready.emit(self._latest_stats)
            self.state_changed.emit("recording_started")

            while not self._stop_event.is_set() or not self._queue.empty():
                try:
                    batch = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                self._latest_stats = self._recorder.write_batch(batch)
                if self._latest_stats.batches_written % 15 == 0:
                    self.stats_ready.emit(self._latest_stats)

            if self._dropped_queue_batches:
                self._recorder.add_dropped_batches(self._dropped_queue_batches)
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("Recording worker failed.")
            self.error.emit(str(exc))
        finally:
            self._latest_stats = self._recorder.stop()
            self.stats_ready.emit(self._latest_stats)
            self.state_changed.emit("recording_stopped")
