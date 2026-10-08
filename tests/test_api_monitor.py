from src.integrations.api_monitor import ApiMonitor


def test_api_monitor_blocks_calls_at_session_limit():
    state = {"api_call_limit": 2}
    monitor = ApiMonitor(state)
    assert monitor.allow_client_call()
    assert monitor.allow_client_call()
    assert not monitor.allow_client_call()
    assert monitor.count == 2
    assert any(row["状态"] == "已阻止" for row in monitor.rows())


def test_api_monitor_records_client_event():
    monitor = ApiMonitor({})
    monitor.record_client_event({
        "request_id": "abc123",
        "operation": "视觉识别",
        "model": "vision/model",
        "status": "失败",
        "elapsed": 1.25,
        "detail": "timeout",
    })
    row = monitor.rows()[0]
    assert row["ID"] == "abc123"
    assert row["状态"] == "失败"
    assert row["详情"] == "timeout"
