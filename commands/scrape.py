import atexit
import subprocess
import time

import click

from voracity2 import settings
from voracity2.commands.reset_site import reset_site
from voracity2.lib import utils
from voracity2.lib.slack import Slack

logger = settings.logger


running_processes: list[tuple[subprocess.Popen, float]] = []


def cleanup_processes():
    """
    Cleanup function to terminate all running subprocesses.
    """
    global running_processes

    for proc, _ in running_processes:
        logger.info(f"Wait for subprocess end. {proc.pid}")
        for i in range(30):
            if proc.poll() is not None:
                break
            time.sleep(1)
        else:
            logger.info(f"Terminating subprocess {proc.pid}")
            proc.terminate()
            proc.wait(timeout=30)  # Wait for the process to terminate
    running_processes.clear()


atexit.register(cleanup_processes)


def _scrape(
    site_name: str,
    target: str,
    proxy_group_name: str | None,
    process: int,
) -> None:
    """
    Internal function to perform scraping for a specific site and target.

    Args:
        site_name (str): スクレイピング対象のサイト名。
        target (str): スクレイピング対象のターゲット（例: "page", "page2", "item"）。
        proxy_group_name (str | None): 使用するプロキシグループ名。指定しない場合はNone。
        process (int): 並列実行するサブプロセス数。

    Returns:
        None
    """
    msg = f"Scraping started for {site_name} with target '{target}'."
    Slack().send_message(msg, settings.SLACK_CHANNEL_NOTIFY_DEBUG)
    logger.info(msg)

    args = ["voracity2", "scrape-one", site_name, target]
    if proxy_group_name:
        args.extend(["-g", proxy_group_name])

    for idx, _ in enumerate(range(process)):
        proc = subprocess.Popen(args)
        running_processes.append((proc, time.time()))
        time.sleep(3)

    while True:
        # logger.info(f"Waiting for {site_name} {target} to finish scraping...")

        # pending(0)が0で、かつ、すべてのプロセスが終了しているか、最後のプロセス開始から2分以上経過している場合にループを抜ける
        # if job.get_pending(site_name, target) == 0 and (
        #     all(p[0].poll() is not None for p in running_processes)
        #     or (time.time() > min(p[1] for p in running_processes) + 120)
        # ):
        #     break
        # else:
        #     time.sleep(5)

        # すべてのサブプロセスが終了している場合
        if all(p[0].poll() is not None for p in running_processes):
            break
        else:
            time.sleep(5)

    cleanup_processes()

    msg = f"Scraping finished for {site_name} with target '{target}'."
    Slack().send_message(msg, settings.SLACK_CHANNEL_NOTIFY_DEBUG)
    logger.info(msg)


@click.command()
@click.argument("site_name")
@click.option("-p", default="auto", help="proxy server ex) http://username:password@proxy:8080")
@click.option("-g", "--proxy-group-name", "proxy_group_name", help="proxy group name")
@click.option("--reset", is_flag=True, default=False, help="reset site info")
@click.option("--process", "-P", type=int, default=1, help="number of processes to use")
def scrape_command(
    site_name: str,
    proxy_group_name: str,
    p: str | None,
    reset: bool,
    process: int,
) -> None:
    """
    Command to scrape a specific site with optional proxy settings and reset option.
    """
    site_id = utils.get_site_id(site_name)
    if not site_id:
        msg = f"Invalid site name: {site_name}. Please check the site name and try again."
        Slack().send_message(msg, settings.SLACK_CHANNEL_NOTIFY_DEBUG)
        logger.error(msg)
        return

    if reset:
        logger.info(f"Resetting site info for {site_name}.")
        reset_site(site_name)

    _scrape(site_name, "page", proxy_group_name if proxy_group_name else site_name, process)
    _scrape(site_name, "page2", proxy_group_name if proxy_group_name else site_name, process)
    _scrape(site_name, "item", proxy_group_name if proxy_group_name else site_name, process)
