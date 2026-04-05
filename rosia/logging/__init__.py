import logging

import rerun as rr
from rich.console import Console

from rosia.time import Time
from rosia.rerun import RerunManager
from collections.abc import Iterable
from rerun._baseclasses import AsComponents, DescribedComponentBatch

from typing import TYPE_CHECKING
from typing import Optional

if TYPE_CHECKING:
    from rosia.config import RerunConfig

_LEVEL_STYLES = {
    logging.DEBUG: "dim",
    logging.INFO: "bold blue",
    logging.WARNING: "bold yellow",
    logging.ERROR: "bold red",
    logging.CRITICAL: "bold white on red",
}


class Logger:
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    def __init__(self, name: str = "rosia") -> None:
        self._name = name
        self._level = logging.INFO
        self._console: Console | None = None
        self._trace = False
        self._rerun_manager: Optional[RerunManager] = None
        self.logical_time = Time(0)
        self.physical_time = Time(0)

    @property
    def console(self) -> Console:
        if self._console is None:
            self._console = Console(stderr=True)
        return self._console

    def set_logical_time(self, logical_time: Time) -> None:
        self.logical_time = logical_time

    def set_physical_time(self, physical_time: Time) -> None:
        self.physical_time = physical_time

    def set_trace(self, trace: bool) -> None:
        self._trace = trace

    def set_rerun_config(self, rerun_config: "RerunConfig") -> None:
        self._rerun_manager = RerunManager()
        self._rerun_manager.init(rerun_config)

    def _log(self, level: int, msg: str, rerun_subpath: str = "") -> None:
        if self._level <= level:
            style = _LEVEL_STYLES.get(level, "")
            self.console.print(
                f"[{style}]\\[{self._name}] {msg}[/{style}]", highlight=False
            )
        if self._trace and self._rerun_manager is not None:
            self._rerun_manager.log(
                f"trace/{self._name}/{rerun_subpath}",
                rr.TextLog(text=str(msg), level="DEBUG"),
                self.logical_time,
                self.physical_time,
            )

    def rerun(
        self,
        msg: AsComponents | Iterable[DescribedComponentBatch],
        rerun_subpath: str = "",
    ) -> None:
        if self._rerun_manager is not None:
            self._rerun_manager.log(
                f"/logs/{self._name}/{rerun_subpath}",
                msg,
                self.logical_time,
                self.physical_time,
            )

    def shutdown(self) -> None:
        if self._rerun_manager is not None:
            self._rerun_manager.shutdown()

    def set_level(self, level: int) -> None:
        self._level = level

    def debug(self, msg: str, rerun_subpath: str = "") -> None:
        self._log(logging.DEBUG, msg, rerun_subpath)

    def info(self, msg: str, rerun_subpath: str = "") -> None:
        self._log(logging.INFO, msg, rerun_subpath)

    def warning(self, msg: str, rerun_subpath: str = "") -> None:
        self._log(logging.WARNING, msg, rerun_subpath)

    def error(self, msg: str, rerun_subpath: str = "") -> None:
        self._log(logging.ERROR, msg, rerun_subpath)

    def critical(self, msg: str, rerun_subpath: str = "") -> None:
        self._log(logging.CRITICAL, msg, rerun_subpath)
