"""Gradium streamed WAVs carry placeholder RIFF/data sizes; _fix_wav_header
rewrites them from the real byte length so <audio> duration/scrubbing works."""

import io
import wave

from ghostpanel.voice.gradium_voice import _fix_wav_header


def _wav_with_placeholder_sizes(seconds: float = 2.0, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    data = bytearray(buf.getvalue())
    # Corrupt sizes the way a streaming encoder does (0xFFFFFFFF placeholders).
    data[4:8] = b"\xff\xff\xff\xff"
    at = bytes(data).find(b"data", 12)
    data[at + 4:at + 8] = b"\xff\xff\xff\xff"
    return bytes(data)


def test_fixes_placeholder_duration():
    broken = _wav_with_placeholder_sizes(seconds=2.0)
    fixed = _fix_wav_header(broken)
    with wave.open(io.BytesIO(fixed)) as w:
        assert abs(w.getnframes() / w.getframerate() - 2.0) < 0.01


def test_correct_wav_is_unchanged():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000)
    good = buf.getvalue()
    assert _fix_wav_header(good) == good


def test_non_wav_bytes_pass_through():
    assert _fix_wav_header(b"not audio") == b"not audio"
