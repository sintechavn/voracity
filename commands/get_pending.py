import click

from voracity2.lib import job


@click.command()
@click.argument("site_name", type=str)
@click.argument("target", type=str)
def get_pending_command(site_name: str, target: str) -> None:
    """
    Command to get pending jobs for a specific site and target."""
    pending = job.get_pending(site_name, target)
    print(pending)
    return
