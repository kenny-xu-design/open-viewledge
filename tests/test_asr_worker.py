from __future__ import annotations

import queue
import multiprocessing
import time
import unittest
from pathlib import Path

from src.asr_worker import LocalASRWorkerError, LocalASRWorkerRunner
from src.config import AppConfig


TELEMETRY = {
    "profile": "balanced",
    "model": "small",
    "device": "cpu",
    "compute_type": "int8",
    "batch_size": 1,
    "beam_size": 1,
}


def sleeping_worker(*args):
    time.sleep(5)


class FakeQueue:
    def __init__(self, messages):
        self.messages = list(messages)
        self.closed = False
        self.joined = False
        self.cancelled = False

    def get(self, timeout):
        if self.messages:
            return self.messages.pop(0)
        raise queue.Empty

    def close(self):
        self.closed = True

    def join_thread(self):
        self.joined = True

    def cancel_join_thread(self):
        self.cancelled = True


class FakeConnection:
    def __init__(self, incoming=None):
        self.incoming = list(incoming or [])
        self.sent = []
        self.closed = False

    def poll(self, timeout=0):
        return bool(self.incoming)

    def recv(self):
        return self.incoming.pop(0)

    def send(self, value):
        self.sent.append(value)

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, *, stays_alive=True):
        self.alive = stays_alive
        self.exitcode = None
        self.terminated = False
        self.killed = False
        self.closed = False

    def start(self):
        return None

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True
        self.alive = False
        self.exitcode = -15

    def kill(self):
        self.killed = True
        self.alive = False
        self.exitcode = -9

    def join(self, timeout=None):
        return None

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, messages, *, stays_alive=True):
        terminal = [
            item for item in messages if item.get("type") in {"result", "error"}
        ]
        events = [
            item for item in messages if item.get("type") not in {"result", "error"}
        ]
        self.queue = FakeQueue(events)
        self.process = FakeProcess(stays_alive=stays_alive)
        self.result_receiver = FakeConnection(terminal)
        self.result_sender = FakeConnection()
        self.control_receiver = FakeConnection()
        self.control_sender = FakeConnection()
        self.pipe_calls = 0

    def Queue(self):
        return self.queue

    def Process(self, **kwargs):
        return self.process

    def Pipe(self, duplex=False):
        self.pipe_calls += 1
        if self.pipe_calls == 1:
            return self.result_receiver, self.result_sender
        return self.control_receiver, self.control_sender


class LocalASRWorkerRunnerTests(unittest.TestCase):
    def test_success_streams_segments_and_returns_result(self) -> None:
        context = FakeContext(
            [
                {"type": "model_loaded"},
                {"type": "transcribing"},
                {"type": "heartbeat"},
                {"type": "segment", "start": 0, "end": 1, "text": "测试"},
                {
                    "type": "result",
                    "segments": [{"index": 0, "start": 0, "end": 1, "text": "测试"}],
                    "telemetry": TELEMETRY,
                },
            ]
        )
        events = []
        outcome = LocalASRWorkerRunner(
            project_root=Path.cwd(), process_context=context
        ).run(
            Path("same-audio.wav"),
            config=AppConfig(
                asr_gpu_model_load_timeout_seconds=0.2,
                asr_transcribe_stall_timeout_seconds=0.2,
            ),
            device="cpu",
            language="zh",
            event_callback=events.append,
        )
        self.assertEqual(outcome.segments[0].text, "测试")
        self.assertIn("segment", [item["type"] for item in events])
        self.assertTrue(context.process.terminated)
        self.assertTrue(context.process.closed)
        self.assertTrue(context.queue.closed)
        self.assertTrue(context.queue.joined)
        self.assertEqual(context.control_sender.sent, ["ack"])

    def test_gpu_model_load_timeout_terminates_worker(self) -> None:
        context = FakeContext([])
        with self.assertRaises(LocalASRWorkerError) as raised:
            LocalASRWorkerRunner(
                project_root=Path.cwd(), process_context=context
            ).run(
                Path("same-audio.wav"),
                config=AppConfig(asr_gpu_model_load_timeout_seconds=0.02),
                device="cuda",
                language="zh",
            )
        self.assertEqual(raised.exception.reason, "gpu_model_load_timeout")
        self.assertTrue(raised.exception.timed_out)
        self.assertTrue(context.process.terminated)
        self.assertFalse(context.process.is_alive())

    def test_gpu_heartbeat_without_segment_still_stalls(self) -> None:
        context = FakeContext(
            [
                {"type": "model_loaded"},
                {"type": "transcribing"},
                *[{"type": "heartbeat"} for _ in range(4)],
            ]
        )
        with self.assertRaises(LocalASRWorkerError) as raised:
            LocalASRWorkerRunner(
                project_root=Path.cwd(), process_context=context
            ).run(
                Path("same-audio.wav"),
                config=AppConfig(
                    asr_gpu_model_load_timeout_seconds=0.2,
                    asr_transcribe_stall_timeout_seconds=0.02,
                ),
                device="cuda",
                language="zh",
            )
        self.assertEqual(raised.exception.reason, "gpu_transcription_stalled")
        self.assertTrue(context.process.terminated)

    def test_cpu_stall_is_terminal(self) -> None:
        context = FakeContext(
            [{"type": "model_loaded"}, {"type": "transcribing"}]
        )
        with self.assertRaises(LocalASRWorkerError) as raised:
            LocalASRWorkerRunner(
                project_root=Path.cwd(), process_context=context
            ).run(
                Path("same-audio.wav"),
                config=AppConfig(
                    asr_gpu_model_load_timeout_seconds=0.2,
                    asr_transcribe_stall_timeout_seconds=0.02,
                ),
                device="cpu",
                language="zh",
            )
        self.assertEqual(raised.exception.reason, "cpu_transcription_stalled")
        self.assertTrue(raised.exception.timed_out)
        self.assertTrue(context.process.terminated)

    def test_real_timeout_process_is_not_left_running(self) -> None:
        context = multiprocessing.get_context("spawn")
        before = {process.pid for process in multiprocessing.active_children()}
        runner = LocalASRWorkerRunner(
            project_root=Path.cwd(),
            process_context=context,
            worker_target=sleeping_worker,
        )
        with self.assertRaises(LocalASRWorkerError) as raised:
            runner.run(
                Path("same-audio.wav"),
                config=AppConfig(asr_gpu_model_load_timeout_seconds=0.05),
                device="cuda",
                language="zh",
            )
        self.assertEqual(raised.exception.reason, "gpu_model_load_timeout")
        remaining = {
            process.pid
            for process in multiprocessing.active_children()
            if process.pid not in before
        }
        self.assertEqual(remaining, set())


if __name__ == "__main__":
    unittest.main()
