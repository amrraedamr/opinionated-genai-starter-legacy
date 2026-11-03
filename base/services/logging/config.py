LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s[%(asctime)s] %(levelname)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "white",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
        "simple": {
            "format": "{log:%(message)s}",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "colored",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


def get_logging_config(environment: str) -> dict:
    config = dict(LOGGING_CONFIG)
    if environment != "local":
        config["formatters"] = {
            "json": {
                "()": "base.services.logging.json_formatter.JsonFormatter",
            }
        }
        config["handlers"] = {
            "console": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        }
    return config
