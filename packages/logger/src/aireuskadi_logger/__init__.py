"""JSON logging for the Python services: one JSON object per line on standard output."""

from aireuskadi_logger.logs import JsonFormatter, configure_logging

__all__ = ["JsonFormatter", "configure_logging"]
