import logging
from collections import deque
from typing import List


class InMemoryHandler(logging.Handler):
    def __init__(self, maxlen: int = 200):
        super().__init__()
        self.buffer = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.buffer.append(msg)

    def get_logs(self) -> List[str]:
        return list(self.buffer)


_handler: InMemoryHandler | None = None


def setup_logger(name: str = "email-orchestrator") -> logging.Logger:
    global _handler
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.setLevel(logging.INFO)
        logger.addHandler(console)

        _handler = InMemoryHandler(maxlen=500)
        _handler.setFormatter(fmt)
        logger.addHandler(_handler)

    return logger


def get_recent_logs() -> List[str]:
    if _handler is None:
        return []
    return _handler.get_logs()


logger = setup_logger()
