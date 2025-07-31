from persai.server import get_server
from persai.logging import configure_logging
import os

configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
)

app = get_server()
