import logging
import pytest

from daily_read import utils

log = logging.getLogger(__name__)
error_handler = utils.ErrorCollectorHandler()
log.root.addHandler(error_handler)


def test_error_reporting_without_error():
    """Test that no error is raised when the log has no error messages"""
    for handler in log.root.handlers:
        if isinstance(handler, utils.ErrorCollectorHandler):
            handler.error_messages = []
    log.info("Test info")
    log.warning("Warn message")
    try:
        utils.error_reporting(log)
    except RuntimeError:
        assert False, "This should not raise an exception"


def test_error_reporting_with_error():
    """Test error thrown when the log has error messages"""
    for handler in log.root.handlers:
        if isinstance(handler, utils.ErrorCollectorHandler):
            handler.error_messages = []
    error_message = "Test error message"
    log.error(error_message)
    with pytest.raises(RuntimeError, match=f"Errors logged in DailyRead during execution\n{error_message}"):
        utils.error_reporting(log)
