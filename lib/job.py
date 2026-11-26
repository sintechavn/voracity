from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from voracity2 import settings
from voracity2.lib import utils
from voracity2.models.category import Category
from voracity2.models.crawl_logs import CrawlLog
from voracity2.models.database import engine
from voracity2.models.page_ import Page_

logger = settings.logger


@contextmanager
def get_db_session():
    """データベースセッションのコンテキストマネージャー"""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def cleanup_running_jobs():
    """
    Cleanup running jobs in the database.
    """
    # 1時間以上Running(1)の状態のページがあったら、Pending(0)に戻す
    with get_db_session() as session:
        session.query(Page_).filter(
            Page_.status == 1, Page_.updated_at < datetime.now() - timedelta(minutes=10)
        ).update({"status": 0})
        session.commit()


def get_job_progress() -> list[dict]:
    """
    Get job progress from the database.
    """
    # ページのステータスを取得する
    with get_db_session() as session:
        result = [
            dict(row)
            for row in session.execute(text("SELECT * FROM v_status2 WHERE site_id IS NOT NULL AND site_id NOT IN (26, 938, 940) ORDER BY site_id;")).mappings()
        ]
    return result

def get_page_progress_by_id(site_id: int) -> int:
    with get_db_session() as session:
        statement = text("SELECT page_progress FROM v_status WHERE site_id = :site_id")
        result = session.execute(statement, {"site_id": site_id}).scalar()
        
        return result if result is not None else 0

def get_job_progress_to_report() -> list[dict]:
    """
    Get job progress from the database.
    """
    # ページのステータスを取得する
    with get_db_session() as session:
        result = [
            dict(row)
            for row in session.execute(text("SELECT * FROM v_status2 WHERE site_id IS NOT NULL AND site_id NOT IN (26, 938, 940) ORDER BY site_id;")).mappings()
        ]
    return result

def create_log(site_id: int) -> bool:
    statement = text("""
               insert into crawl_logs (
                    site_id,
                    site_name,
                    page_pending,
                    page_running,
                    page_end_ok,
                    page_end_ng,
                    page_total,
                    product_total)
                select
                    site_id,
                    site_name,
                    page_pending,
                    page_running,
                    page_end_ok,
                    page_end_ng,
                    page_total,
                    product_total
                from
                    v_status2
                where
                    site_id = :site_id
                    and product_total > 0
                """)
    with get_db_session() as session:
        ret = session.execute(statement, {"site_id": site_id})
        session.commit()
        if ret.rowcount > 0:
            return True
        else:
            return False

def get_last_product_count(site_id: int) -> int:
    """
    Get the last product count from the database.
    """
    with get_db_session() as session:
        log = (
            session.query(CrawlLog.product_total)
            .filter(CrawlLog.site_id == site_id)
            .order_by(CrawlLog.id.desc())
            .limit(1)
            .first()
        )
        if not log:
            return 0
        else:
            return log.product_total


def progress_to_str(progress: list[dict]) -> str:
    """
    Convert the progress list to a string format.
    """

    message = "\n".join(
        [
            f'{p["site_name"]} {p["page_end_ok"]+p["page_end_ng"]:,}/{p["page_total"]:,} {p["page_progress"]}% ({p["product_total"]:,}件)'
            for p in progress
        ]
    )

    return message


def get_pending(site_name: str, target: str) -> int:
    """
    Get job progress for a specific site and target.
    """
    match target:
        case "page":
            return _get_pending_category(site_name)
        case "page2":
            return _get_pending_page(f"temp#{site_name}")
        case "item":
            return _get_pending_page(site_name)
        case _:
            raise ValueError(f"Unknown target: {target}")


def _get_pending_page(site_name: str) -> int:
    """
    Get job progress for a specific site.
    """
    site_id = utils.get_site_id(site_name)
    with get_db_session() as session:
        result = (
            session.query(Page_.status).filter(Page_.site_id == site_id, Page_.status == 0).count()
        )
        session.commit()

        if result:
            return result
        else:
            return 0


def _get_pending_category(site_name: str) -> int:
    """
    Get job progress for a specific site.
    """
    site_id = utils.get_site_id(site_name)
    with get_db_session() as session:
        result = (
            session.query(Category.status)
            .filter(Category.site_id == site_id, Category.status == 0)
            .count()
        )
        session.commit()

        if result:
            return result
        else:
            return 0


def get_status(site_name: str | None = None) -> dict | list[dict]:
    """
    Get job progress from the database.
    """
    with get_db_session() as session:
        if site_name:
            # ページのステータスを取得する
            result = [
                dict(row)
                for row in session.execute(
                    text("SELECT * FROM v_status2 where site_name=:site_name order by site_id;"),
                    {"site_name": site_name},
                ).mappings()
            ]
            if result:
                return result[0]
            else:
                return {}
        else:
            # ページのステータスを取得する
            result = [
                dict(row)
                for row in session.execute(
                    text("SELECT * FROM v_status2 order by site_id;")
                ).mappings()
            ]
            return result

def has_pending_pages(site_id: int) -> bool:
    """
    Check if there are any pages with status 0 or 1.
    """
    with get_db_session() as session:
        result = (
            session.query(Page_.status)
            .filter(Page_.site_id == site_id, Page_.status.in_([0, 1]))
            .first()
        )
        if result:
            return True
        else:
            return False

def check_progress_and_update(site_id: int) -> Optional[float]:
    """
    Evaluates the page_progress delta.
    Returns the difference (float) IF AN ALERT SHOULD BE SENT (i.e., progress grew by < 10%).
    Returns None if progress is fine, it's the first run, or last progress was already 100%.
    Updates or initializes the site_last_progress table with the current value.
    """
    with get_db_session() as session:
        # Fetch current progress and site name from the view
        current_status = session.execute(
            text("SELECT page_progress, site_name FROM v_status WHERE site_id = :site_id"),
            {"site_id": site_id}
        ).fetchone()

        # Abort comparison if site_id is not present in the status view
        if not current_status:
            logger.warning(f"Could not find status for site_id: {site_id}")
            return None

        current_progress = float(current_status.page_progress or 0)
        site_name = current_status.site_name
        
        # We will store the calculated difference here if it's too slow
        alert_diff = None

        # Fetch previously recorded progress
        last_progress_record = session.execute(
            text("SELECT page_progress FROM site_last_progress WHERE site_id = :site_id"),
            {"site_id": site_id}
        ).fetchone()

        # Calculate difference if historical data exists
        if last_progress_record is not None:
            last_progress = float(last_progress_record.page_progress or 0)

            # Skip the alert check entirely if the scraper was already at 100% last time
            if last_progress < 100.0:
                diff = current_progress - last_progress
                
                # If the difference is LESS than 10%, the scraper is stalled -> Send Alert
                if 0 <= diff < 10.0:
                    alert_diff = round(diff, 2) # Rounds to 2 decimal places (e.g., 7.2)

            # Update the existing record with the new value
            session.execute(
                text("UPDATE site_last_progress SET page_progress = :current_progress WHERE site_id = :site_id"),
                {"current_progress": current_progress, "site_id": site_id}
            )
        else:
            # Handle first-run scenario: No previous record exists to compare against.
            session.execute(
                text("INSERT INTO site_last_progress (site_id, site_name, page_progress) VALUES (:site_id, :site_name, :current_progress)"),
                {"site_id": site_id, "site_name": site_name, "current_progress": current_progress}
            )

        session.commit()
        
        # Returns the float difference if slow, otherwise returns None
        return alert_diff

def check_scraping_eta(site_id: int) -> Dict[str, Any]:
    """
    Calculates progress metrics and delay days for a specific site.
    """
    with get_db_session() as session:
        # 1. Fetch start date (earliest product created)
        start_record = session.execute(
            text("SELECT MIN(created_at) as start_date FROM pages_new WHERE site_id = :site_id"),
            {"site_id": site_id}
        ).fetchone()

        # 2. Fetch current progress
        status_record = session.execute(
            text("SELECT page_progress FROM v_status WHERE site_id = :site_id"),
            {"site_id": site_id}
        ).fetchone()

        if not start_record or not start_record.start_date or not status_record:
            return {}

        start_date = start_record.start_date
        current_progress = float(status_record.page_progress or 0)
        now = datetime.now()

        # 3. Calculations
        days_passed = max((now - start_date).total_seconds() / (24 * 3600), 0.1)
        # Original 10-day deadline
        end_date_deadline = start_date + timedelta(days=10) 

        days_delayed = 0
        if current_progress > 0:
            actual_speed_per_day = current_progress / days_passed
            estimated_total_days = 100.0 / actual_speed_per_day
            days_delayed = max(0, round(estimated_total_days - 10, 1))

        return {
            "start_date": start_date, # Added this
            "end_date": end_date_deadline.strftime('%Y/%m/%d'),
            "days_delayed": days_delayed
        }
