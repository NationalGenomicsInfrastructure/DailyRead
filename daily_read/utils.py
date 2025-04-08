"""Module for common utility functions"""

import logging
import subprocess
import sys


class ContextFilter(logging.Filter):
    """
    This is a filter which injects contextual information into the log.

    """

    def filter(self, record):
        """Inject commit_id into the log"""
        record.commit = get_git_commits()["git_commit"]
        return True


def get_git_commits():
    git_commits = {}
    try:
        git_commits["git_commit"] = (
            subprocess.check_output(["git", "rev-parse", "--short=7", "HEAD"]).decode(sys.stdout.encoding).strip()
        )
        git_commits["git_commit_full"] = (
            subprocess.check_output(["git", "rev-parse", "HEAD"]).decode(sys.stdout.encoding).strip()
        )
    except:
        git_commits["git_commit"] = "unknown"
        git_commits["git_commit_full"] = "unknown"
    return git_commits

class ErrorCollectorHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.error_messages = []

    def emit(self, record):
        # Collect error-level log messages
        if record.levelno >= logging.ERROR:
            self.error_messages.append(record.msg)

# Rudimentary Error reporting
def error_reporting(log):
    """Raise an error if there are Error level messages in the daily_read module logs"""
    error_string = ""
    for handler in log.root.handlers:
        if isinstance(handler, ErrorCollectorHandler):
            if handler.error_messages:
                error_string = "Errors logged in DailyRead during execution\n"
                error_string += "\n".join(handler.error_messages)

    if error_string:
        # Suppress traceback
        sys.tracebacklimit = 0
        raise RuntimeError(error_string)
