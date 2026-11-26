import os
import zipfile
import shutil
import time
from datetime import date
from tempfile import TemporaryDirectory

import click
import polars as pl

from voracity2 import settings
from voracity2.commands import reset_site
from voracity2.lib import job, utils
from voracity2.lib.slack import Slack

logger = settings.logger
header_mapping = {
    "id": "id",
    "site_id": "site_id",
    "url": "URL",
    "name": "Name",
    "brand": "Brand",
    "product_code": "ProductCode",
    "product_code2": "ProductCode2",
    "sku": "Sku",
    "color": "color",
    "gender": "Gender",
    "category1": "Category1",
    "category2": "Category2",
    "category3": "Category3",
    "category4": "Category4",
    "category5": "Category5",
    "category6": "Category6",
    "category7": "Category7",
    "category8": "Category8",
    "category9": "Category9",
    "category10": "Category10",
    "price": "Price",
    "sale_price": "SalePrice",
    "currency": "Currency",
    "size": "Size",
    "image1": "Image1",
    "image2": "Image2",
    "image3": "Image3",
    "image4": "Image4",
    "image5": "Image5",
    "image6": "Image6",
    "image7": "Image7",
    "image8": "Image8",
    "image9": "Image9",
    "image10": "Image10",
}


def export_item(site_id: int, output_fpath: str, database_url: str):
    encoding = "utf_8_sig" if site_id == 1 else "shift_jis"
    
    cols = ",".join([f"{h1} as {h2}" for h1, h2 in header_mapping.items()])
    sql = f"SELECT {cols} FROM products_new where site_id={site_id} and status=2"

    with open(output_fpath, "w", encoding=encoding, errors="ignore") as f:
        f.write(
            pl.read_database_uri(
                sql,
                database_url,
            )
            .select(header_mapping.values())
            .write_csv()
        )

def export_item_backup(site_id: int, output_fpath: str, database_url: str):
    encoding = "utf_8_sig" if site_id == 1 else "shift_jis"
 
    cols = ",".join([f"{h1} as {h2}" for h1, h2 in header_mapping.items()])
    sql = f"SELECT {cols} FROM products_new_backup where site_id={site_id} and status=2"

    with open(output_fpath, "w", encoding=encoding, errors="ignore") as f:
        f.write(
            pl.read_database_uri(
                sql,
                database_url,
            )
            .select(header_mapping.values())
            .write_csv()
        )

def make_zip(input_fpath: str):
    output_fname = os.path.basename(input_fpath)

    with zipfile.ZipFile(
        f"{input_fpath}.zip",
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        zf.write(input_fpath, arcname=output_fname)

def send_csv(site_name: str, force_flg: bool, reset_flg: bool, backup_flg: bool) -> None:
    today = date.today().strftime("%Y%m%d")
    site_id = utils.get_site_id(site_name)
    if not site_id:
        logger.error(f"Invalid site name: {site_name}")
        return

    # check if any page is still in progress
#    if job.has_pending_pages(site_id):
#        logger.info(f"{site_name} まだ処理中のページがあります。")
#        if not force_flg:
#            return
    page_progress = job.get_page_progress_by_id(site_id)
    if page_progress < 98:
        message = f"{site_name}: Tiến độ thu thập chỉ đạt {page_progress}%, thấp hơn ngưỡng 96%."
        logger.error(message)
        # Gửi cảnh báo lỗi về Slack
        if not force_flg:
            return

    product_total = job.get_status(site_name).get("product_total")
    if not product_total or product_total == 0:
        message = f"{site_name}の製品データがありません。"
        logger.error(message)
        Slack().send_message(channel=settings.SLACK_CHANNEL_NOTIFY_DEBUG, message=message)
        if not force_flg:
            return

    last_product_count = job.get_last_product_count(site_id)
    if last_product_count * 0.8 > product_total:
        message = f"{site_name}のデータ件数が少ないです。確認してください 前回: {last_product_count:,} 件 今回: {product_total:,} 件"
        logger.warning(message)
        Slack().send_message(channel=settings.SLACK_CHANNEL_NOTIFY_DEBUG, message=message)
        if not force_flg:
            return

    logger.info(
        f"{site_name} 送信処理開始 前回 {last_product_count:,}件 -> 今回 {product_total:,}件"
    )

    with TemporaryDirectory() as tmpdir:
        ## CSVファイルを作成する
        fpath = f"{tmpdir}/{site_name}_{today}.csv"
        if backup_flg:
            export_item_backup(site_id, fpath, settings.DATABASE_URL)
        else:
            export_item(site_id, fpath, settings.DATABASE_URL)
        make_zip(fpath)
        logger.info(f"{site_name} {fpath}.zip 作成完了")

	# copy to temp_csv
        try:
            os.makedirs(settings.TEMP_CSV_DIR, exist_ok=True)
            shutil.copy(f"{fpath}.zip", settings.TEMP_CSV_DIR)
            logger.info(f"{site_name} temp_csvにコピー完了")
        except Exception as e:
            logger.error(f"{site_name} temp_csvにコピー失敗: {e}")

        ## CSVファイルをSlackで送信する
        Slack().send_file(
            file_path=f"{fpath}.zip",
            message=f"{site_name}({site_id}) の取得が完了しました。{product_total}件",
            channel="C0A123G3KLZ",
        )
        logger.info(f"{site_name} {fpath}.zip Slack送信完了")

    # NOTE: crawl_logs への記録は send_csv_real のみが行う

    ## サイトの情報をリセットする
    if reset_flg:
        reset_site.reset_site(site_name)
        logger.info(f"{site_name} サイト情報リセット完了")
"""
def send_csv_real(site_name: str, force_flg: bool, reset_flg: bool) -> None:
    today = date.today().strftime("%Y%m%d")
    site_id = utils.get_site_id(site_name)
    if not site_id:
        logger.error(f"Invalid site name: {site_name}")
        return

    if job.has_pending_pages(site_id):
        logger.info(f"{site_name} まだ処理中のページがあります。")
        if not force_flg:
            return

    try:
        product_total = job.get_status(site_name).get("product_total")
        if not product_total:
            message = f"{site_name}の製品データがありません。"
            logger.error(message)
            Slack().send_message(message=message, channel="C0A3LEF26Q7")
            return

        last_product_count = job.get_last_product_count(site_id)
        if last_product_count * 0.8 > product_total:
            message = f"{site_name}のデータ件数が少ないです。確認してください 前回: {last_product_count:,} 件 今回: {product_total:,} 件"
            logger.warning(message)
            Slack().send_message(message=message, channel="C0A3LEF26Q7")
            if not force_flg:
                return

        logger.info(f"{site_name} 送信処理開始 前回 {last_product_count:,}件 -> 今回 {product_total:,}件")

        with TemporaryDirectory() as tmpdir:
            fpath = f"{tmpdir}/{site_name}_{today}.csv"
            export_item(site_id, fpath, settings.DATABASE_URL)
            make_zip(fpath)
            logger.info(f"{site_name} {fpath}.zip 作成完了")

            try:
                os.makedirs(settings.TEMP_CSV_DIR, exist_ok=True)
                shutil.copy(f"{fpath}.zip", settings.TEMP_CSV_DIR)
                logger.info(f"{site_name} temp_csvにコピー完了")
            except Exception as e:
                logger.error(f"{site_name} temp_csvにコピー失敗: {e}")
                raise

            Slack().send_file_real(
                file_path=f"{fpath}.zip",
                message=f"{site_name}({site_id}) の取得が完了しました。{product_total}件"
            )
            logger.info(f"{site_name} {fpath}.zip Slack送信完了")

        if not job.create_log(site_id):
            raise Exception(f"{site_name} ログ記録失敗")
        
        logger.info(f"{site_name} ログ記録完了")

        if reset_flg:
            reset_site.reset_site(site_name)
            logger.info(f"{site_name} サイト情報リセット完了")

    except Exception as e:
        logger.error(f"{site_name} エラーが発生したため、リセット処理は実行されません: {e}")
"""

def send_csv_real(site_name: str, force_flg: bool, reset_flg: bool) -> None:
    today = date.today().strftime("%Y%m%d")
    site_id = utils.get_site_id(site_name)
    if not site_id:
        logger.error(f"Invalid site name: {site_name}")
        return
    if job.has_pending_pages(site_id):
        logger.info(f"{site_name} まだ処理中のページがあります。")
        if not force_flg:
            return
    try:
        product_total = job.get_status(site_name).get("product_total")
        if not product_total:
            message = f"{site_name}の製品データがありません。"
            logger.error(message)
           # Slack().send_message(message=message, channel="C0A3LEF26Q7")
            return
        last_product_count = job.get_last_product_count(site_id)
        if last_product_count * 0.8 > product_total:
            message = f"{site_name}のデータ件数が少ないです。確認してください 前回: {last_product_count:,} 件 今回: {product_total:,} 件"
            logger.warning(message)
            Slack().send_message(message=message, channel="C0A3LEF26Q7")
            if not force_flg:
                return
        logger.info(f"{site_name} 送信処理開始 前回 {last_product_count:,}件 -> 今回 {product_total:,}件")

        backup_zip_path = f"{settings.TEMP_CSV_DIR}/{site_name}_{today}.csv.zip"

        with TemporaryDirectory() as tmpdir:
            fpath = f"{tmpdir}/{site_name}_{today}.csv"
            export_item(site_id, fpath, settings.DATABASE_URL)
            make_zip(fpath)
            logger.info(f"{site_name} {fpath}.zip 作成完了")
            try:
                os.makedirs(settings.TEMP_CSV_DIR, exist_ok=True)
                shutil.copy(f"{fpath}.zip", settings.TEMP_CSV_DIR)
                logger.info(f"{site_name} temp_csvにコピー完了")
            except Exception as e:
                logger.error(f"{site_name} temp_csvにコピー失敗: {e}")
                raise
            Slack().send_file_real(
                file_path=f"{fpath}.zip",
                message=f"{site_name}({site_id}) の取得が完了しました。{product_total}件"
            )
            logger.info(f"{site_name} {fpath}.zip Slack送信完了")

        if not job.create_log(site_id):
            raise Exception(f"{site_name} ログ記録失敗")
        logger.info(f"{site_name} ログ記録完了")

        if reset_flg:
            # --- Xác minh CSV đã export & backup tồn tại trước khi reset ---
            if not os.path.exists(backup_zip_path):
                logger.error(
                    f"{site_name} バックアップファイルが見つからないため、リセットをスキップします: {backup_zip_path}"
                )
                Slack().send_message(
                    message=f"{site_name} のリセットをスキップしました（バックアップファイル未確認: {backup_zip_path}）",
                    channel="C0A3LEF26Q7"
                )
            else:
                reset_site.reset_site(site_name)
                logger.info(f"{site_name} サイト情報リセット完了")
    except Exception as e:
        logger.error(f"{site_name} エラーが発生したため、リセット処理は実行されません: {e}")

@click.command()
@click.argument("site_name")
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
@click.option(
    "--backup",
    "backup_flg",
    is_flag=True,
    default=False,
    help="Sending CSV of backup data",
)
def send_csv_command(site_name: str, force_flg: bool, reset_flg: bool, backup_flg: bool) -> None:
    """
    Command to send CSV files.
    """
    send_csv(site_name, force_flg, reset_flg, backup_flg)

@click.command()
@click.argument("site_name")
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
def send_csv_by_hour_command(site_name: str, force_flg: bool, reset_flg: bool) -> None:
    """
    Command to send CSV files by hour.
    """
    send_csv_by_hour(site_name, force_flg, reset_flg)

@click.command()
@click.argument("site_name")
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

def send_csv_real_command(site_name: str, force_flg: bool, reset_flg: bool) -> None:
    """
    Command to send CSV files to customer's Slack.
    """
    send_csv_real(site_name, force_flg, reset_flg)


@click.command()
@click.argument("site_name")
def check_pending_command(site_name: str) -> None:
    """
    Command to check if site has any pending status.
    """
    site_id = utils.get_site_id(site_name)
    if not site_id:
        logger.error(f"Invalid site name: {site_name}")
        return

    if job.has_pending_pages(site_id):
        logger.info(f"{site_name} is still pending.")
    else:
        logger.info(f"{site_name} has finished crawled.")

@click.command()
def delete_csv_command() -> None:
    """
    Command to delete CSV/ZIP files from temp_csv folder older than 10 days.
    """
    folder_path = "temp_csv"
    retention_days = 10
    now = time.time()
    cutoff_time = now - (retention_days * 86400)

    if not os.path.exists(folder_path):
        logger.warning(f"Folder {folder_path} does not exist.")
        return

    logger.info(f"Checking for files older than {retention_days} days in {folder_path}...")

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if not os.path.isfile(file_path):
            continue
            
        try:
            file_creation_time = os.path.getctime(file_path)
            if file_creation_time < cutoff_time:
                os.remove(file_path)
                logger.info(f"Deleted old file: {filename}")
        except Exception as e:
            logger.error(f"Failed to delete {filename}: {e}")
