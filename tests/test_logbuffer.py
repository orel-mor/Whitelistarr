import logging

from app.logbuffer import LogBuffer


def _record(level, msg):
    return logging.LogRecord("test", level, __file__, 1, msg, None, None)


def test_default_buffer_holds_1000_lines():
    from app.logbuffer import LOG_BUFFER, LogBuffer

    assert LogBuffer()._records.maxlen == 1000
    assert LOG_BUFFER._records.maxlen == 1000


def test_tail_returns_only_last_n():
    buf = LogBuffer(capacity=100)
    for i in range(20):
        buf.handle(_record(logging.INFO, f"m{i}"))
    msgs = [r["message"] for r in buf.records(tail=3)]
    assert msgs == ["m17", "m18", "m19"]


def test_tail_larger_than_available_returns_all():
    buf = LogBuffer(capacity=100)
    buf.handle(_record(logging.INFO, "only"))
    assert [r["message"] for r in buf.records(tail=50)] == ["only"]


def test_tail_applies_after_level_filter():
    buf = LogBuffer(capacity=100)
    buf.handle(_record(logging.DEBUG, "dbg"))
    buf.handle(_record(logging.ERROR, "e1"))
    buf.handle(_record(logging.ERROR, "e2"))
    msgs = [r["message"] for r in buf.records(level="ERROR", tail=1)]
    assert msgs == ["e2"]


def test_keeps_last_n_records():
    buf = LogBuffer(capacity=3)
    for i in range(5):
        buf.handle(_record(logging.INFO, f"m{i}"))
    lines = buf.records()
    assert [r["message"] for r in lines] == ["m2", "m3", "m4"]


def test_each_record_has_increasing_id():
    buf = LogBuffer(capacity=10)
    buf.handle(_record(logging.INFO, "a"))
    buf.handle(_record(logging.INFO, "b"))
    ids = [r["id"] for r in buf.records()]
    assert ids == sorted(ids)
    assert ids[0] < ids[1]


def test_records_after_id_returns_only_newer():
    buf = LogBuffer(capacity=10)
    buf.handle(_record(logging.INFO, "a"))
    first = buf.records()[0]["id"]
    buf.handle(_record(logging.INFO, "b"))
    newer = buf.records(after=first)
    assert [r["message"] for r in newer] == ["b"]


def test_filters_by_minimum_level():
    buf = LogBuffer(capacity=10)
    buf.handle(_record(logging.DEBUG, "dbg"))
    buf.handle(_record(logging.WARNING, "warn"))
    buf.handle(_record(logging.ERROR, "err"))
    msgs = [r["message"] for r in buf.records(level="WARNING")]
    assert msgs == ["warn", "err"]


def test_record_exposes_level_name_and_message():
    buf = LogBuffer(capacity=10)
    buf.handle(_record(logging.ERROR, "kaboom"))
    rec = buf.records()[0]
    assert rec["level"] == "ERROR"
    assert rec["message"] == "kaboom"
    assert "time" in rec


def test_setup_logging_writes_to_rolling_file(tmp_path):
    from logging.handlers import RotatingFileHandler

    from app.main import setup_logging

    f = tmp_path / "whitelistarr.log"
    try:
        setup_logging("info", log_file=str(f), log_file_lines=10000)
        assert any(
            isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers
        )
        logging.getLogger("file-write-test").info("line-to-file-xyz")
        assert "line-to-file-xyz" in f.read_text(encoding="utf-8")
    finally:
        setup_logging("info")  # reset root handlers (drop the tmp file handler)


def test_setup_logging_no_file_when_path_empty():
    from logging.handlers import RotatingFileHandler

    from app.main import setup_logging

    setup_logging("info", log_file="")
    assert not any(
        isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers
    )


def test_setup_logging_installs_buffer_on_root():
    from app.logbuffer import LOG_BUFFER
    from app.main import setup_logging

    setup_logging("info")
    assert LOG_BUFFER.handler() in logging.getLogger().handlers
    logging.getLogger("setup-wire-test").info("captured-by-root")
    assert LOG_BUFFER.records()[-1]["message"] == "captured-by-root"


def test_as_logging_handler_captures_through_logger():
    buf = LogBuffer(capacity=10)
    logger = logging.getLogger("logbuffer-test")
    logger.setLevel(logging.INFO)
    logger.addHandler(buf.handler())
    try:
        logger.info("hello %s", "world")
    finally:
        logger.removeHandler(buf.handler())
    assert buf.records()[-1]["message"] == "hello world"
