import logging
from pathlib import Path

import yaml
from platformdirs import PlatformDirs

PACKAGE_ROOT = Path(__file__).parent.resolve()
TEMP_CSV_DIR = PACKAGE_ROOT / "temp_csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)s %(message)s",
)
logger = logging.getLogger(__name__)


DATABASE_URL = "sqlite:///data.db"
SLACK_BEARER_TOKEN = ""
SLACK_CHANNEL_DELIVERY = ""
SLACK_CHANNEL_DELIVERY_DEBUG = ""
SLACK_CHANNEL_NOTIFY = ""
SLACK_CHANNEL_NOTIFY_DEBUG = ""

_dirs = PlatformDirs("voracity2", "handc")

config_fpath = Path(_dirs.user_config_dir, "config.yaml")

print('config_fpath', config_fpath)
