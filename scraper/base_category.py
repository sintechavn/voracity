import logging
import random
import socket
import time
from collections.abc import Generator
from datetime import datetime

from patchright.sync_api import BrowserContext, sync_playwright
from patchright.sync_api import Page as PRPage
from sqlalchemy import exc as sa_exc
from sqlalchemy.dialects.mysql import insert

from voracity2.lib.utils import Status
from voracity2.models.category import Category
from voracity2.models.database import session
from voracity2.models.page_ import Page_

# ロガーの設定
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BaseCategoryScraper:
    site_id: int = 0
    domain: str = ""
    hostname: str = socket.gethostname()
    block_status: list[int] = [403, 423]
    sleep_time: int = 1800
    browser_args: dict = {"args": ["--disable-features=Translate"]}
    context_args: dict = {}
    ctx: BrowserContext | None = None
    prpage: PRPage | None = None
    max_page_locator: str | None = None

    def __init__(self, browser_args: dict = {}, context_args: dict = {}):
        """
        初期化メソッド。Playwrightのブラウザとコンテキストを設定します。

        Args:
            **kwargs: ブラウザ起動時の追加パラメータ。
        """
        self.plw = sync_playwright().start()
        self.browser = self.plw.chromium.launch(
            channel="chrome",
            headless=False,
            **self.browser_args,
        )
        self.ctx = self.get_context()

    def crawl(self):
        """
        クロール処理を実行します。
        """

        categories = [c for c in self.get_next()]
        self.save_categories(categories)

    def get_context(self) -> BrowserContext:
        if self.ctx is not None:
            return self.ctx
        else:
            self.ctx = self.browser.new_context(no_viewport=True, **self.context_args)
            page = self.ctx.new_page()
            page.goto(f"https://{self.domain}/")
            page.wait_for_timeout(10000)
            page.close()
            return self.ctx

    def close_context(self):
        if self.ctx is not None:
            self.ctx.close()
            self.ctx = None

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
                "site_id": self.site_id,
                "category_id": category.id,
                "category_url": category.url,
                "status": Status.PENDING,
                "url": self.get_listpage_url(category.url, page_no),
                "sku": f"{category.id}#{page_no}",
                "updated_at": datetime.now(),
                "updated_by": self.hostname,
            }

    def get_next(self) -> Generator[Category, None, None]:
        """
        次のカテゴリを取得します。

        Yields:
            Category: 次のカテゴリオブジェクト。
        """
        while True:
            try:
                category = (
                    session.query(Category)
                    .filter(Category.site_id == self.site_id, Category.status == Status.PENDING)
                    .limit(1)
                    .with_for_update()
                    .one()
                )
                category.status = Status.RUNNING
                category.updated_at = datetime.now()
                category.updated_by = self.hostname
                category.result_text = None
                session.commit()
                yield category
            except sa_exc.NoResultFound:
                session.rollback()
                logger.info("No more category")
                break
            except Exception as e:
                session.rollback()
                logger.error(f"{type(e)}: {str(e)}")

    def get_prpage_by_url(self, url: str, wait_for: str | None = None) -> PRPage | None:
        """
        指定されたURLのページを取得します。

        Args:
            url (str): ページのURL。

        Returns:
            PRPage | None: ページオブジェクトまたはNone。
        """
        prpage = self.get_context().new_page()

        response = prpage.goto(url, timeout=20000)
        if wait_for is not None:
            prpage.wait_for_selector(wait_for, timeout=20000)

        if response.status in self.block_status:
            logger.warning(f"{response.status}:blocked. sleep {self.sleep_time}sec:{url}")
            time.sleep(self.sleep_time)
        elif response.status == 404:
            logger.info(f"{response.status}:page not found:{url}")
            return None
        elif response.status >= 400:
            time.sleep(random.uniform(5, 10))
            raise Exception(f"{response.status}:goto failed. {response.status_text}:{url}")
        else:
            return prpage

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

    def update_status(
        self, obj: Category | Page_, new_status: Status, result_text: str = ""
    ) -> bool:
        """
        ページのステータスを更新します。

        Args:
            page (DBPage): データベースページオブジェクト。
            new_status (Status): 新しいステータス。
            result_text (str, optional): 結果テキスト。デフォルトは空文字列。

        Returns:
            bool: 更新が成功したかどうか。
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

    def save_categories(self, categories: list[dict]):
        """
        データベースにカテゴリ情報を保存します。

        Args:
            categories (list[dict]): 保存するカテゴリ情報のリスト。
        """
        insert_stmt = insert(Category.__table__).values(categories)
        update_dict = {
            col.name: insert_stmt.inserted[col.name] for col in Category.__table__.columns
        }
        update_stmt = insert_stmt.on_duplicate_key_update(**update_dict)
        session.execute(update_stmt)
        session.commit()
