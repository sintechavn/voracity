from datetime import datetime, timedelta

import click

from voracity2 import settings
from voracity2.models.database import session
from voracity2.models.page_ import Page_

logger = settings.logger


def cleanup_running():
    """
    Cleanup running jobs in the database.
    """
    # 1時間以上Running(1)の状態のページがあったら、Pending(0)に戻す
    session.query(Page_).filter(
        Page_.status == 1, Page_.updated_at < datetime.now() - timedelta(minutes=10)
    ).update({"status": 0})
    session.commit()


@click.command()
def cleanup_running_command():
    """
    Command to clean up running jobs."""
    cleanup_running()
