"""Tests for vaulls.settlement."""

import json
from unittest.mock import patch

from vaulls.config import configure, reset_config
from vaulls.settlement import enable_settlement_log, log_settlement


class TestSettlementLog:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_log_to_jsonl(self, tmp_path):
        log_file = tmp_path / "test.jsonl"
        configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        enable_settlement_log(path=str(log_file))

        entry = log_settlement(
            tool="POST /tools/test",
            price="$0.05",
            payer="0xBUYER",
            tx_hash="0xTX123",
            network="eip155:84532",
            latency_ms=42.567,
        )

        assert entry["tool"] == "POST /tools/test"
        assert entry["latency_ms"] == 42.6  # rounded

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        saved = json.loads(lines[0])
        assert saved["tx_hash"] == "0xTX123"
        assert "timestamp" in saved

    def test_log_with_callback(self):
        captured = []
        configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        enable_settlement_log(callback=captured.append)

        log_settlement(
            tool="POST /tools/cb-test",
            price="$0.10",
            payer="0xBUYER",
            tx_hash="0xTX456",
            network="eip155:84532",
            latency_ms=10.0,
        )

        assert len(captured) == 1
        assert captured[0]["tool"] == "POST /tools/cb-test"

    def test_no_logging_when_not_enabled(self, tmp_path):
        configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        # Don't call enable_settlement_log

        entry = log_settlement(
            tool="POST /tools/silent",
            price="$0.01",
            payer="0xBUYER",
            tx_hash="0xTX789",
            network="eip155:84532",
            latency_ms=5.0,
        )

        # Entry is still returned even if not persisted
        assert entry["tool"] == "POST /tools/silent"

    def test_log_both_file_and_callback(self, tmp_path):
        log_file = tmp_path / "both.jsonl"
        captured = []
        configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        enable_settlement_log(path=str(log_file), callback=captured.append)

        log_settlement(
            tool="POST /tools/both",
            price="$0.05",
            payer="0xBUYER",
            tx_hash="0xTXBOTH",
            network="eip155:84532",
            latency_ms=20.0,
        )

        assert len(captured) == 1
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1


class TestSettlementRetry:
    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    def test_retry_succeeds_after_transient_failure(self, tmp_path):
        log_file = tmp_path / "retry.jsonl"
        configure(
            pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b",
            settlement_max_retries=2,
            settlement_retry_delay=0.01,
        )
        enable_settlement_log(path=str(log_file))

        call_count = 0
        original_open = open

        def flaky_open(path, mode="r", **kwargs):
            nonlocal call_count
            if str(log_file) in str(path) and mode == "a":
                call_count += 1
                if call_count == 1:
                    raise OSError("Transient disk error")
            return original_open(path, mode, **kwargs)

        with patch("builtins.open", side_effect=flaky_open):
            entry = log_settlement(
                tool="POST /tools/retry-test",
                price="$0.05",
                payer="0xBUYER",
                tx_hash="0xTXRETRY",
                network="eip155:84532",
                latency_ms=10.0,
            )

        assert entry["tool"] == "POST /tools/retry-test"
        # Should have been called twice (1 failure + 1 success)
        assert call_count == 2
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_max_retries_exhausted(self, tmp_path):
        log_file = tmp_path / "fail.jsonl"
        configure(
            pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b",
            settlement_max_retries=2,
            settlement_retry_delay=0.01,
        )
        enable_settlement_log(path=str(log_file))

        with patch("builtins.open", side_effect=OSError("Persistent failure")):
            entry = log_settlement(
                tool="POST /tools/fail-test",
                price="$0.05",
                payer="0xBUYER",
                tx_hash="0xTXFAIL",
                network="eip155:84532",
                latency_ms=10.0,
            )

        # Entry is still returned even though logging failed
        assert entry["tool"] == "POST /tools/fail-test"
        # File should not exist since all writes failed
        assert not log_file.exists()

    def test_zero_retries_is_single_attempt(self, tmp_path):
        """Default max_retries=0 means single attempt — no retry."""
        log_file = tmp_path / "noretry.jsonl"
        configure(pay_to="0x7863A5c4396E7aaac2e99Cb649a7Aa4F6A36B91b")
        enable_settlement_log(path=str(log_file))

        call_count = 0
        original_open = open

        def counting_open(path, mode="r", **kwargs):
            nonlocal call_count
            if str(log_file) in str(path) and mode == "a":
                call_count += 1
                raise OSError("Disk error")
            return original_open(path, mode, **kwargs)

        with patch("builtins.open", side_effect=counting_open):
            log_settlement(
                tool="POST /tools/noretry",
                price="$0.05",
                payer="0xBUYER",
                tx_hash="0xTXNO",
                network="eip155:84532",
                latency_ms=10.0,
            )

        # Should only attempt once (no retries)
        assert call_count == 1
