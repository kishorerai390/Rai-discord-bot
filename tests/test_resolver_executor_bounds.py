from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

from music_bot.services import resolver_service


class TestResolverExecutorBounds(unittest.IsolatedAsyncioTestCase):
    async def test_timed_out_worker_keeps_capacity_until_thread_exits(self):
        executor = ThreadPoolExecutor(max_workers=1)
        started = threading.Event()
        release = threading.Event()
        second_call_started = threading.Event()

        def slow_call():
            started.set()
            release.wait(timeout=5)
            return "finished"

        try:
            with patch.object(resolver_service, "_audio_executor", executor):
                with self.assertRaises(asyncio.TimeoutError):
                    await resolver_service._run_ytdlp(
                        slow_call,
                        timeout=0.05,
                        operation="test_timeout",
                        correlation_id="TEST-TIMEOUT",
                    )

                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                with self.assertRaises(asyncio.TimeoutError):
                    await resolver_service._run_ytdlp(
                        lambda: second_call_started.set(),
                        timeout=0.05,
                        operation="test_saturation",
                        correlation_id="TEST-SATURATION",
                    )

                self.assertFalse(second_call_started.is_set())
                release.set()
                result = await resolver_service._run_ytdlp(
                    lambda: "capacity-released",
                    timeout=1,
                    operation="test_cleanup",
                    correlation_id="TEST-CLEANUP",
                )
                self.assertEqual(result, "capacity-released")
        finally:
            release.set()
            executor.shutdown(wait=True)

    async def test_cancellation_does_not_release_running_worker_slot_early(self):
        executor = ThreadPoolExecutor(max_workers=1)
        started = threading.Event()
        release = threading.Event()

        def slow_call():
            started.set()
            release.wait(timeout=5)

        try:
            with patch.object(resolver_service, "_audio_executor", executor):
                task = asyncio.create_task(
                    resolver_service._run_ytdlp(
                        slow_call,
                        timeout=2,
                        operation="test_cancel",
                        correlation_id="TEST-CANCEL",
                    )
                )
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

                with self.assertRaises(asyncio.TimeoutError):
                    await resolver_service._run_ytdlp(
                        lambda: None,
                        timeout=0.05,
                        operation="test_cancel_saturation",
                        correlation_id="TEST-CANCEL-SATURATION",
                    )

                release.set()
                result = await resolver_service._run_ytdlp(
                    lambda: "capacity-released",
                    timeout=1,
                    operation="test_cancel_cleanup",
                    correlation_id="TEST-CANCEL-CLEANUP",
                )
                self.assertEqual(result, "capacity-released")
        finally:
            release.set()
            executor.shutdown(wait=True)

    async def test_worker_logs_do_not_include_exception_secrets(self):
        executor = ThreadPoolExecutor(max_workers=1)
        secret = "authorization=private-test-value"

        try:
            with patch.object(resolver_service, "_audio_executor", executor):
                with self.assertLogs(resolver_service.logger, level="WARNING") as captured:
                    with self.assertRaisesRegex(RuntimeError, "private-test-value"):
                        await resolver_service._run_ytdlp(
                            lambda: (_ for _ in ()).throw(RuntimeError(secret)),
                            timeout=1,
                            operation="test_redaction",
                            correlation_id="TEST-REDACTION",
                        )
            self.assertNotIn(secret, "\n".join(captured.output))
            self.assertIn("exception_type=RuntimeError", "\n".join(captured.output))
            safe_error = resolver_service._format_error(
                RuntimeError(
                    "authorization=private-test-value\n"
                    "cookie: session=private-cookie\n"
                    "https://example.test/audio?signature=private-signature"
                )
            )
            self.assertNotIn("private-test-value", safe_error)
            self.assertNotIn("private-cookie", safe_error)
            self.assertNotIn("private-signature", safe_error)
            self.assertIn("[REDACTED]", safe_error)
            self.assertIn("[URL redacted]", safe_error)
        finally:
            executor.shutdown(wait=True)

    async def test_youtube_options_keep_certificate_verification_enabled(self):
        options = resolver_service._build_ytdl_options(["android"])
        self.assertNotIn("nocheckcertificate", options)


if __name__ == "__main__":
    unittest.main()
