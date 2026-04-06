"""Mikrofon-Aufnahme mit sounddevice."""

import threading
import numpy as np
import sounddevice as sd
from src.config import SAMPLE_RATE, CHANNELS


class Recorder:
    """Nimmt Audio vom Mikrofon auf (16kHz, mono, float32 für Whisper)."""

    def __init__(self):
        self._chunks = []
        self._lock = threading.Lock()
        self._stream = None
        self.is_recording = False

    def start(self):
        """Aufnahme starten."""
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        self.is_recording = True

    def stop(self):
        """Aufnahme stoppen, Audio als numpy-Array zurückgeben."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.is_recording = False

        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            self._chunks = []
        return audio

    def get_audio_snapshot(self):
        """Gibt den bisherigen Audio-Puffer zurück OHNE die Aufnahme zu stoppen."""
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            return np.concatenate(list(self._chunks), axis=0).flatten()

    def take_chunks(self):
        """Holt alle bisherigen Audio-Chunks ab und leert den Puffer.

        Die Aufnahme läuft weiter — neue Chunks werden ab jetzt gesammelt.
        Gibt das Audio als numpy-Array zurück.
        """
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            self._chunks = []
        return audio

    def _callback(self, indata, frames, time, status):
        """Stream-Callback — Audio-Chunks sammeln."""
        with self._lock:
            self._chunks.append(indata.copy())
