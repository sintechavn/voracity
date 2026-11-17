import multiprocessing as mp
from logging import getLogger

import click

from voracity2.commands.cleanup_running import cleanup_running_command
from voracity2.commands.get_pending import get_pending_command
from voracity2.commands.progress import get_progress_command, send_progress_command, check_all_progress_command
from voracity2.commands.proxy_check import proxy_check_all, proxy_get
from voracity2.commands.reset_site import reset_site_command
from voracity2.commands.scrape import scrape_command
from voracity2.commands.scrape_one import scrape_one_command
from voracity2.commands.send_csv import send_csv_command, send_csv_by_hour_command, send_csv_real_command, check_pending_command, delete_csv_command
from voracity2.commands.send_csv_all import send_csv_all_command
from voracity2.commands.bot_test import bot_test

logger = getLogger(__name__)


@click.group()
def cli():
    """
    Voracity2 CLI entry point.
    """
    mp.freeze_support()
    pass


cli.add_command(send_csv_command)
cli.add_command(send_csv_all_command)
cli.add_command(send_csv_by_hour_command)
cli.add_command(send_csv_real_command)
cli.add_command(get_pending_command)
cli.add_command(reset_site_command)
cli.add_command(cleanup_running_command)
cli.add_command(scrape_command)
cli.add_command(scrape_one_command)
cli.add_command(proxy_check_all)
cli.add_command(proxy_get)
cli.add_command(get_progress_command)
cli.add_command(send_progress_command)
cli.add_command(bot_test)
cli.add_command(check_pending_command)
cli.add_command(delete_csv_command)
cli.add_command(check_all_progress_command)

if __name__ == "__main__":
    mp.freeze_support()
    cli()
