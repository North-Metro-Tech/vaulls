"""Tests for vaulls.settlement."""

import json

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
