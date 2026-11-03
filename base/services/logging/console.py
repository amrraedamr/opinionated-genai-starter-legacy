import logging
import logging.config
from typing import Any

from base.models.definitions.exceptions import ExceptionCategory
from base.services.common.meta import Singleton
from base.services.configuration import settings
from base.services.logging import LogMessage
from base.services.logging.config import get_logging_config


class ConsoleLoggerService(metaclass=Singleton):
    def __init__(self) -> None:
        logging.config.dictConfig(get_logging_config(settings.environment))
        self._logger: logging.Logger = logging.getLogger()

    def info(self, message: LogMessage, *args: Any) -> None:
        self._logger.info(message, *args)

    def error(
        self,
        message: LogMessage,
        *args: Any,
        status: str | int | None = None,
        category: ExceptionCategory | None = ExceptionCategory.INTERNAL,
        location: str | None = None,
        tag: str = "Internal",
    ) -> None:
        self._logger.error(
            self._format_error(
                message, status=status, category=category, location=location, tag=tag
            ),
            *args,
        )

    def exception(
        self,
        message: LogMessage,
        *args: Any,
        status: str | int | None = None,
        category: ExceptionCategory | None = ExceptionCategory.INTERNAL,
        location: str | None = None,
        tag: str = "Internal",
    ) -> None:
        self._logger.exception(
            self._format_error(
                message, status=status, category=category, location=location, tag=tag
            ),
            *args,
        )

    def warning(self, message: LogMessage, *args: Any) -> None:
        self._logger.warning(message, *args)

    def debug(self, message: LogMessage, *args: Any) -> None:
        self._logger.debug(message, *args)

    @staticmethod
    def _format_error(
        message: LogMessage,
        *,
        status: str | int | None,
        category: ExceptionCategory | None,
        location: str | None,
        tag: str,
    ) -> str:
        return f"[Code: {status}] [Category: {category}] [Location: {location}] [Tag: {tag}] {message}"
