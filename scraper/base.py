import random
import re
import socket
import time
from abc import ABC, abstractmethod
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import parsel
from bs4 import BeautifulSoup
from sqlalchemy import exc as sa_exc
from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert

from voracity2 import settings
from voracity2.lib.utils import Status
from voracity2.lib.web_provider import FetchpageResponse, WebProvider
from voracity2.models.category import Category
from voracity2.models.database import session
from voracity2.models.item import Item
from voracity2.models.page_ import Page_
from voracity2.settings import logger


class BaseScraper(ABC):
    hostname: str = socket.gethostname()

    site_id: int = 0
    site_name: str = ""
    domain: str = ""
    not_found_status: list[int] = [404]
    not_found_messages: list[str] = []
    block_status: list[int] = [403, 423]
    block_messages: list[str] = []
    sleep_time: int = 3600  # 1時間
    cookies: list[dict] | None = None
    headers: dict = {}
    randomize_location: bool = False
    popup_locator: str | None = None

    page_wait_for: str | None = None
    page_scroll_to_line: int = 0
    max_page_locator: str | None = None

    page2_wait_for: str | None = None
    page2_scroll_to_line: int = 0
    item_locator: str = ""

    item_wait_for: str | None = None
    item_scroll_to_line: int = 0

    def __init__(self, web_provider: WebProvider, options: dict = {}):
        """
        初期化メソッド。Playwrightのブラウザとコンテキストを設定
        """
        self.options = options
        self.proxy: str | None = options.get("proxy")
        self.web = web_provider

    def crawl_page(self):
        """
        カテゴリからリストページを取得
        """

        for c in self._get_next(self.site_id, Category):
            category: Category = c
            try:
                logger.info(category.url)
                response: FetchpageResponse = self.web.fetch_page(
                    url=category.url,
                    wait_for=self.page_wait_for,
                    cookies=self.cookies,
                    headers=self.headers | {"referer": "www.google.com"},
                    not_found_status=self.not_found_status,
                    not_found_messages=self.not_found_messages,
                    block_status=self.block_status,
                    block_messages=self.block_messages,
                    scroll_to_line=self.page_scroll_to_line,
                    popup_locator=self.popup_locator,
                )
                if response.status_code in self.not_found_status:
                    self.update_status(category, Status.END_ERROR, "Page not found")
                    continue

                max_page_no: int | None = self.get_max_page_no(response.text)
                if max_page_no is None:
                    self.update_status(
                        category, Status.END_ERROR, f"category:{category.id}, Max page not found"
                    )
                    continue

                logger.info(f"category:{category.id}, max_page_no:{max_page_no}")
                listpages = [listpage for listpage in self.get_listpage(category, max_page_no)]
                self.save_data(listpages, Page_)
                self.update_status(category, Status.END_OK, "OK")

                time.sleep(random.uniform(2, 6))

            except Exception as e:
                if category:
                    logger.error(
                        f"ID:{category.id}, URL:{category.url}, type:{type(e)}, message:{str(e)}"
                    )
                else:
                    logger.error(f"type:{type(e)}, message:{str(e)}")

                if "response" in locals():
                    (settings.TEMP_DIR / Path("base_page_error.html")).write_text(
                        response.text, encoding="utf-8"
                    )
                self.update_status(category, Status.PENDING, str(e))

        self.end_crawl()

    def get_listpage(self, category: Category, max_page_no: int) -> Generator[dict, None, None]:
        """
        リストページを生成します。

        Args:
            category (Category): カテゴリオブジェクト。
            max_page_no (int): 最大ページ番号。

        Yields:
            dict: リストページ情報の辞書。
        """
        for page_no in range(1, max_page_no + 1):
            yield {
                "site_id": self.site_id + 900,
                "category_id": category.id,
                "category_url": category.url,
                "status": Status.PENDING,
                "url": self.get_listpage_url(category.url, page_no),
                "sku": f"{category.id}#{page_no}",
                "updated_at": datetime.now(),
                "updated_by": self.hostname,
            }

    def get_producturl(self, url: str) -> str:
        """
        商品URLを取得します。

        Args:
            url (str): 商品のURL。

        Returns:
            str: 正規化された商品URL。
        """
        url = url.replace("&amp;", "&")

        if url.startswith("https://"):
            return url
        elif url.startswith("/"):
            return f"https://{self.domain}{url}"
        else:
            return f"https://{self.domain}/{url}"

    def get_listpage_url(self, category_url: str, page_no: int) -> str:
        """
        リストページのURLを取得します。

        Args:
            category_url (str): カテゴリのURL。
            page_no (int): ページ番号。

        Returns:
            str: リストページのURL。
        """
        # 実装が必要
        raise NotImplementedError

    def get_max_page_no(self, html: str) -> int:
        """
        最大ページ番号を取得します。

        Args:
            html (str): ページのHTMLコンテンツ。

        Returns:
            int: 最大ページ番号。
        """
        # 実装が必要
        raise NotImplementedError

    def end_crawl(self) -> None:
        """
        クロール終了後の処理を定義します。
        """
        self.web.close_driver()

    def _get_next(self, site_id: int, model_class: type) -> Generator[type, None, None]:
        """
        次のページを取得

        Args:
            site_id (int): サイトID
            model_class (type): モデルクラス

        Yields:
            model_class: 次のページオブジェクト
        """
        while True:
            try:
                page: Page_ = (
                    session.query(model_class)
                    .filter(model_class.site_id == site_id, model_class.status == Status.PENDING)
                    .order_by(func.rand())
                    .limit(1)
                    .with_for_update()
                    .one()
                )
                page.status = Status.RUNNING
                page.updated_at = datetime.now()
                page.updated_by = self.hostname
                page.result_text = None
                session.commit()
                yield page
            except sa_exc.NoResultFound:
                session.rollback()
                logger.info("No more page")
                break
            except Exception as e:
                session.rollback()
                logger.error(f"{type(e)}: {str(e)}")

    def update_status(
        self, obj: Page_ | Category, new_status: Status, result_text: str = ""
    ) -> bool:
        """
        ページのステータスを更新

        Args:
            obj (Page_|Category): データベースページオブジェクト
            new_status (Status): 新しいステータス
            result_text (str, optional): 結果テキスト。デフォルトは空文字列

        Returns:
            bool: 更新が成功したかどうか
        """
        try:
            obj.status = new_status
            obj.result_text = result_text[:190]
            obj.updated_at = datetime.now()
            obj.updated_by = self.hostname
            session.commit()
            return True
        except Exception as e:
            logger.error(f"{type(e)}: {str(e)}")
            session.rollback()
            return False

    def save_data(self, items: list[dict], model_class: type) -> None:
        """
        データを保存します。

        Args:
            items (list[dict]): 保存するデータのリスト。
        """
        insert_stmt = insert(model_class.__table__).values(items)
        update_dict = {
            col.name: insert_stmt.inserted[col.name] for col in model_class.__table__.columns
        }
        update_stmt = insert_stmt.on_duplicate_key_update(**update_dict)
        session.execute(update_stmt)
        session.commit()

    def get_abs_url(self, url: str) -> str:
        if url.startswith("http"):
            return url
        elif url.startswith("/"):
            return f"https://{self.domain}{url}"
        else:
            return f"https://{self.domain}/{url}"

    def crawl_page2(self):
        """
        クロール処理を実行します。
        """
        for p in self._get_next(self.site_id + 900, Page_):
            page_: Page_ = p
            try:
                logger.info(page_.url)
                response: FetchpageResponse = self.web.fetch_page(
                    page_.url,
                    wait_for=self.item_locator,
                    cookies=self.cookies,
                    headers=self.headers,
                    not_found_status=self.not_found_status,
                    not_found_messages=self.not_found_messages,
                    block_status=self.block_status,
                    block_messages=self.block_messages,
                    scroll_to_line=self.page2_scroll_to_line,
                    popup_locator=self.popup_locator,
                )
                if response.status_code == 404:
                    self.update_status(page_, Status.END_ERROR, "Page not found")
                    continue
                item_pages: list[dict] = [p for p in self.parse_listpage(page_, response.text)]
                self.save_data(item_pages, Page_)
                self.update_status(page_, Status.END_OK, "OK")
            except Exception as e:
                logger.error(f"{type(e)}: {str(e)}")
                self.update_status(page_, Status.END_ERROR, str(e))

        self.end_crawl()

    def parse_listpage(self, page_: Page_, html: str):
        """
        リストページを解析します。

        Args:
            page_ (Page_): リストページオブジェクト。
            driver (Any): ドライバオブジェクト。
        """
        # self.web.random_action()

        parser = parsel.Selector(html)

        for idx, elem in enumerate(parser.xpath(self.item_locator), start=1):
            item_url = self.get_itemurl(elem.attrib["href"])
            sku = self.get_sku(page_, item_url)
            logger.info(f"{idx}: {item_url}")

            if self.item_exists(sku):
                logger.info(f"page:{page_.id}: SKIP item {item_url} exists")
                continue

            yield {
                "site_id": self.site_id,
                "category_id": page_.category_id,
                "category_url": page_.category_url,
                "status": Status.PENDING,
                "url": item_url,
                "sku": sku,
                "updated_at": datetime.now(),
                "updated_by": self.hostname,
            }

    def get_itemurl(self, url: str) -> str:
        """
        商品URLを取得します。

        Args:
            url (str): 商品のURL。

        Returns:
            str: 正規化された商品URL。
        """
        url = url.replace("&amp;", "&")

        if url.startswith("https://"):
            return url
        elif url.startswith("/"):
            return f"https://{self.domain}{url}"
        else:
            return f"https://{self.domain}/{url}"

    def item_exists(self, sku: str) -> bool:
        """
        商品が存在するかどうかを確認します。

        Args:
            url (str): 商品のURL。

        Returns:
            bool: 商品が存在する場合はTrue、存在しない場合はFalse。
        """
        ret = (
            session.query(Item)
            .filter(
                Item.site_id == self.site_id,
                Item.sku == sku,
            )
            .limit(1)
            .first()
        )
        if ret is None:
            return False
        else:
            return True

    @abstractmethod
    def get_sku(self, page_: Page_, item_url: str) -> str:
        """
        SKUを取得します。

        Args:
            page_ (Page_): リストページオブジェクト。
            item_url (str): 商品のURL。

        Returns:
            str: SKU。
        """
        raise NotImplementedError("crawl method must be implemented in subclasses")

    def crawl_item(self):
        """
        クロール処理を実行します。
        """
        for _page_ in self._get_next(self.site_id, Page_):
            page_: Page_ = _page_
            try:
                logger.info(page_.url)
                response: FetchpageResponse = self.web.fetch_page(
                    page_.url,
                    wait_for=self.item_wait_for,
                    cookies=self.cookies,
                    headers=self.headers,
                    not_found_status=self.not_found_status,
                    not_found_messages=self.not_found_messages,
                    block_status=self.block_status,
                    block_messages=self.block_messages,
                    scroll_to_line=self.item_scroll_to_line,
                    popup_locator=self.popup_locator,
                )
                if response.status_code == 404:
                    self.update_status(page_, Status.END_ERROR, "Page not found")
                    continue
                try:
                    items: list[dict] = [i for i in self.parse_item(page_, response.text)]
                    if len(items) == 0:
                        raise StopIteration("No items found in the page")
                except StopIteration as e:
                    logger.warning(f"page:{page_.id}: {e.value}")
                    (settings.TEMP_DIR / Path(f"{self.site_name}_item_error.html")).write_text(
                        response.text, encoding="utf-8"
                    )
                    self.update_status(page_, Status.END_ERROR, str(e.value))
                    continue

                self.save_data(items, Item)
                self.update_status(page_, Status.END_OK, "OK")
            except Exception as e:
                logger.error(f"{type(e)}: {str(e)}")
                self.update_status(page_, Status.END_ERROR, str(e))

        self.end_crawl()

    def insert_categories(self, record: dict, categories: list):
        for idx in range(1, 11):
            try:
                category = categories.pop(0)
            except Exception:
                category = None

            record[f"category{idx}"] = category

        return record

    def insert_images(self, record: dict, images: list, start_index: int):
        max_images = 10 - start_index + 1
        if len(images) < max_images:
            images = images + [None] * (max_images - len(images))

        for idx, image in enumerate(images[:max_images], start=start_index):
            record[f"image{idx}"] = image

        return record

    def create_records(self, common_data: dict, variant_data: list | None) -> list[dict]:
        if not variant_data:
            return [common_data] if common_data else []
        records = []
        for data in variant_data:
            data.update(common_data)
            records.append(data)
        return records

    def join_sizes(self, sizes) -> str:
        if None in sizes:
            return "サイズ One-Size"
        parsed_sizes = [re.sub(r" ", "-", size) for size in sizes]
        size_str = " ".join(parsed_sizes)
        return "サイズ " + size_str

    def parse_item(self, html: str, page_: Page_) -> Generator[dict, None, None]:
        """
        商品を解析します。

        Args:
            html (str): 商品ページのHTMLコンテンツ。
            listpage (DBPage): リストページオブジェクト。
            url (str): 商品のURL。

        Yields:
            dict: 商品情報の辞書。
        """
        # To be implemented
        raise NotImplementedError

    def size(self, sizes: list) -> str:
        if len(sizes) == 0:
            return "サイズ one-size"
        sizes = [re.sub(" ", "-", size) for size in sizes]
        size_str = "サイズ " + " ".join(list(set(sizes)))
        return size_str

    def create_soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")
