import click
from sqlalchemy import text

from voracity2 import settings
from voracity2.lib.proxy_manager import ProxyManager
from voracity2.lib.slack import Slack
from voracity2.models.database import session

logger = settings.logger


def get_proxy_status() -> dict:
    """
    Get proxy status from the database.
    """
    # プロキシのステータスを取得する
    result = [
        dict(row)
        for row in session.execute(
            text("SELECT * FROM v_proxy_status order by group_name,status2")
        ).mappings()
    ]
    return result


def notify():
    """
    プロキシの死活状態をSlackに通知する
    """
    _notify()


def status_to_str(status: list[dict]) -> str:
    """
    Convert the progress list to a string format.
    """

    message = "\n".join([f'{s["group_name"]} {s["status2"]}: {s["cnt"]}' for s in status])

    return message


def _notify():
    proxy_status = get_proxy_status()
    logger.info(proxy_status)
    Slack().send_message(status_to_str(proxy_status), settings.SLACK_CHANNEL_NOTIFY_DEBUG)
    logger.info("プロキシのslack通知完了")


@click.command()
def proxy_check_all():
    """
    プロキシのテスト
    """
    proxy_manager = ProxyManager(group_name="default")
    proxy_manager.check_all()
    _notify()


@click.command()
@click.option("--group-name", default="default", help="グループ名")
def proxy_get(group_name: str | None):
    """
    プロキシの取得
    """
    proxy_manager = ProxyManager(group_name)
    proxy = proxy_manager.get()

    if proxy:
        print(f"取得したプロキシ: {proxy}")
    else:
        print("プロキシが見つかりませんでした。")
