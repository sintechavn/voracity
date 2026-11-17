import click
import time
from datetime import datetime, timedelta

from voracity2 import settings
from voracity2.lib import job
from voracity2.lib.slack import Slack


@click.command()
def send_progress_command() -> None:
    """
    Command to send the status of jobs for a specific site.
    """
    status = job.get_job_progress_to_report()

    msg = job.progress_to_str(status)
    #Slack().send_message(msg, settings.SLACK_CHANNEL_NOTIFY)
    Slack().send_message_test(msg, 'C0A3LEF26Q7')

    return


@click.command()
def get_progress_command() -> None:
    """
    Command to send the status of jobs for a specific site."""
    status = job.get_job_progress()

    message = job.progress_to_str(status)
    print(message)

    return

@click.command()
def check_all_progress_command() -> None:
    print("[*] Initiating automated progress validation across all sites...")

    all_jobs_progress = job.get_job_progress()
    if not all_jobs_progress:
        print("[!] No active jobs found in the database.")
        return

    alert_count = 0
    priority_site_ids = [31, 32, 33, 34, 43]

    for project in all_jobs_progress:
        site_id = project.get("site_id")
        site_name = project.get("site_name")

        if not site_id or not site_name:
            continue

        progress_diff = job.check_progress_and_update(site_id)

        if progress_diff is not None:
            # Fetch ETA info which now includes start_date
            eta_info = job.check_scraping_eta(site_id)
            
            # Get start_date from eta_info
            start_date = eta_info.get("start_date")

            if start_date:
                formatted_start = start_date.strftime('%Y/%m/%d')
                ten_days_later = (start_date + timedelta(days=10)).strftime('%Y/%m/%d')
            else:
                formatted_start = "N/A"
                ten_days_later = "N/A"

            # 1. New Header Format
            header_message = (
                f"{site_name}({site_id}) ({progress_diff}% in the last day). "
                f"Start date = {formatted_start}. End date = {ten_days_later}"
            )

            # 2. Detail Message
            if site_id in priority_site_ids and eta_info:
                detail_message = (
                    f"{site_name}({site_id}) crawl speed is slow ({progress_diff}% progress in the last day). "
                    f"End date = {eta_info['end_date']}. "
                    f"Days delayed = {eta_info['days_delayed']}"
                )
            else:
                detail_message = f"{site_name}({site_id}) crawl speed is slow ({progress_diff}% progress in the last day)"

            final_slack_message = f"{header_message}\n{detail_message}"

            try:
                Slack(token=settings.SLACK_BEARER_TOKEN_DEBUG).send_message(
                    final_slack_message, 
                    settings.SLACK_CHANNEL_NOTIFY
                )
                print(f"[!] Alert transmitted for: {site_name}")
                alert_count += 1
            except Exception as e:
                print(f"[✗] Failed to send Slack alert for {site_name}: {e}")

    print(f"\n[✓] Validation sequence complete. {alert_count} alerts dispatched.")
