"""Regression tests for spreadsheet-safe traffic CSV exports."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes import _safe_csv_cell, export_traffic


@pytest.mark.parametrize("formula", [
    "=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)",
    " \t=1+1", "\r\n@SUM(1,2)", "\ufeff=1+1", "\x00=1+1",
])
def test_spreadsheet_formula_prefix_is_escaped(formula):
    assert _safe_csv_cell(formula) == "'" + formula


@pytest.mark.parametrize("ordinary", ["hello", "'=1+1", "some = expression", "", None, 3.5, -12])
def test_csv_escaping_preserves_nonformulas(ordinary):
    assert _safe_csv_cell(ordinary) == ordinary


@pytest.mark.asyncio
async def test_traffic_csv_escapes_prompt_but_json_keeps_original():
    prompt = " \t=HYPERLINK(\"https://example.invalid\",\"label\")"
    record = SimpleNamespace(
        timestamp=datetime(2026, 11, 1, tzinfo=timezone.utc),
        request_id="req_test",
        prompt=prompt,
        task_type="GENERAL_QA",
        complexity="LOW",
        selected_model="mock-balanced",
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        cost_saved=0.0,
        total_latency_ms=12.0,
    )

    class FakeSession:
        async def execute(self, _query):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [record])
            )

    response = await export_traffic(format="csv", db=FakeSession())
    body = b"".join([chunk async for chunk in response.body_iterator]).decode("utf-8")
    row = next(csv.DictReader(io.StringIO(body)))
    assert row["prompt_preview"] == "'" + prompt
    assert row["request_id"] == "req_test"
    assert row["input_tokens"] == "1"

    response_json = await export_traffic(format="json", db=FakeSession())
    assert json.loads(response_json.body)[0]["prompt_preview"] == prompt
