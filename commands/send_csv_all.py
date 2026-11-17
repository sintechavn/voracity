import click

from voracity2 import settings
from voracity2.commands.send_csv import send_csv
from voracity2.lib import job

logger = settings.logger


def send_csv_all(force_flg: bool, reset_flg: bool) -> None:
    for site in job.get_job_progress():
        site_id = site["site_id"]
        site_name = site["site_name"]

        if site_id >= 900:
            logger.info(f"Skipping site {site_name} with ID {site_id} (reserved for future use)")
            continue

        send_csv(site_name=site_name, force_flg=force_flg, reset_flg=reset_flg)


@click.command()
@click.option(
    "--force",
    "force_flg",
    is_flag=True,
    default=False,
    help="Force send CSV even if data count is low",
)
@click.option(
    "--reset",
    "reset_flg",
    is_flag=True,
    default=False,
    help="Reset site information after sending CSV",
)
def send_csv_all_command(force_flg: bool, reset_flg: bool) -> None:
    """
    Command to send CSV files.
    """
    send_csv_all(force_flg, reset_flg)
