import os
import datetime
import sys
import threading

class Logger:
    """
    Logger
    - Creates a 'logs' folder under the provided root_path.
    - Ensures the current day's log file exists on startup.
    - Writes messages prefixed with a timestamp: "[YYYY-MM-DD HH:MM:SS] {message}".
    - Keeps only the last 7 days of log files (deletes older files).
    - Thread-safe for concurrent calls.
    """

    LOG_DIR_NAME = os.path.join("lib", "logs")
    DATE_FORMAT = "%Y-%m-%d"
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
    LOG_RETENTION_DAYS = 7
    FILE_ENCODING = "utf-8"

    def __init__(self, root_path: str, enabled: bool = True):
        """
        Initialize the logger.
        Args:
            root_path: base path where the logs/ folder will be created.
        """
        self.root_path = os.path.abspath(root_path)
        self.logs_path = os.path.join(self.root_path, self.LOG_DIR_NAME)
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        if not self.enabled:
            return

        # Ensure logs directory exists and today's file is present
        try:
            self._ensure_log_dir_and_file()
        except OSError as exc:
            self._report("ERROR", "creating log file", exc)
        # Clean old logs
        self._cleanup_old_logs()

    def _report(self, level: str, operation: str, error: Exception) -> None:
        """Emit a structured fallback when the log file cannot be used."""
        if not self.enabled:
            return
        try:
            sys.stderr.write(
                f"[{level}] [LOGGER] {operation}: {type(error).__name__}: {error}\n"
            )
        except (OSError, ValueError):
            # stderr may be closed during interpreter shutdown; there is no
            # reliable fallback at that point.
            return

    def _ensure_log_dir_and_file(self):
        """Create logs directory and ensure today's log file exists."""
        os.makedirs(self.logs_path, exist_ok=True)
        today_filename = self._filename_for_date(datetime.date.today())
        today_path = os.path.join(self.logs_path, today_filename)
        # Create file if missing
        if not os.path.exists(today_path):
            # Use 'a' to create the file without truncating if concurrently created
            with open(today_path, "a", encoding=self.FILE_ENCODING):
                pass  # just create the file

    def _filename_for_date(self, date_obj: datetime.date) -> str:
        """Return log filename for a given date, e.g., 2025-10-15.log"""
        return f"{date_obj.strftime(self.DATE_FORMAT)}.log"

    def _current_log_path(self) -> str:
        """Return the full path to today's log file."""
        return os.path.join(self.logs_path, self._filename_for_date(datetime.date.today()))

    def _cleanup_old_logs(self):
        """Delete log files older than LOG_RETENTION_DAYS."""
        try:
            cutoff_date = datetime.date.today() - datetime.timedelta(days=self.LOG_RETENTION_DAYS)
            for file_name in os.listdir(self.logs_path):
                # Expect files like YYYY-MM-DD.log
                if not file_name.lower().endswith(".log"):
                    continue
                name_part = file_name[:-4]
                try:
                    file_date = datetime.datetime.strptime(name_part, self.DATE_FORMAT).date()
                except ValueError:
                    # ignore files that don't match the date pattern
                    continue
                if file_date <= cutoff_date:
                    try:
                        os.remove(os.path.join(self.logs_path, file_name))
                    except OSError as exc:
                        self._report("WARN", f"removing old log '{file_name}'", exc)
        except OSError as exc:
            self._report("WARN", "cleaning old logs", exc)

    def write(self, message: str):
        """
        Write a single log line to today's log file.
        The line format is: [YYYY-MM-DD HH:MM:SS] {message}
        Thread-safe.
        """
        if not self.enabled:
            return

        print(message, flush=True)
        timestamp = datetime.datetime.now().strftime(self.TIMESTAMP_FORMAT)
        line = f"[{timestamp}] {message}\n"
        log_path = self._current_log_path()
        with self._lock:
            try:
                log_path = self._current_log_path()
                # Ensure today's file exists (in case date rolled over since init)
                self._ensure_log_dir_and_file()
                with open(log_path, "a", encoding=self.FILE_ENCODING) as f:
                    f.write(line)
            except OSError as exc:
                self._report("ERROR", f"writing '{log_path}'", exc)

    def rotate_if_new_day(self):
        """
        Call this periodically if the process runs across midnight.
        Ensures today's file exists and performs cleanup once per call.
        """
        if not self.enabled:
            return
        with self._lock:
            try:
                self._ensure_log_dir_and_file()
            except OSError as exc:
                self._report("ERROR", "rotating log file", exc)
            self._cleanup_old_logs()
