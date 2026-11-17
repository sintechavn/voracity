import logging
import random
import re
import shutil
import time
from pathlib import Path
from typing import Any, override

from selenium.webdriver.common.keys import Keys
from seleniumbase import Driver

from voracity2.lib.web_provider import FetchpageResponse, WebProvider

logger = logging.getLogger(__name__)

MAX_RETRY: int = 3


class SBProvider(WebProvider):
    popup_loator: str | None = None
    profile_path: Path | None = None

    default_block_messages = [
        "ERR_TIMED_OUT",
        "ERR_TOO_MANY_RETRIES",
        "ERR_TUNNLE_CONNECTION_FAILED",
        "This site can’t be reached",
        "このサイトにアクセスできません",
        "インターネットに接続されていません",
    ]

    @override
    def fetch_page(
        self,
        url: str,
        wait_for: str | None = None,
        sleep_time: int = 1800,
        headers: dict = {},
        cookies: dict = {},
        referer: str | None = None,
        user_agent: str | None = None,
        not_found_status: list[int] = [404],
        not_found_messages: list[str] = [],
        block_status: list[int] = [],
        block_messages: list[str] = [],
        scroll_to_line: int = 0,
        popup_locator: str | None = None,
    ) -> FetchpageResponse:
        """
        指定されたURLのページオブジェクトを取得します。

        Args:
            url (str): ページのURL。

        Returns:
            GetpageResponse | None: GetpageResponseオブジェクトまたはNone。
        """

        retry: int = 0
        self.popup_locator = popup_locator
        while True:
            try:
                driver = self.get_driver()
                start = time.time()
                # driver.execute_script("window.location.href= arguments[0];", url)
                driver.uc_open(url)
                duration = time.time() - start
                if duration > 30:
                    logger.warning(f"Page load time exceeded 30 seconds: {duration}sec: {url}")
                    self.proxy_manager.block(sleep_time)
                    self.close_driver()
                    continue

                if scroll_to_line > 0:
                    self.scroll_to_line(scroll_to_line)

                # メッセージチェック用コンテンツ取得
                for _ in range(5):
                    html = driver.get_page_source()
                    if html is None or html.strip() == "":
                        logger.warning(f"Page source is empty, retrying: {url}")
                        driver.refresh()
                        time.sleep(2)
                    else:
                        break

                if msg := self.message_exists(not_found_messages, html):
                    logger.warning(f"{msg} exist! page not found!")
                    return FetchpageResponse(
                        status_code=404,
                        text=html,
                        ok=False,
                        driver=driver,
                    )

                if msg := self.message_exists(self.default_block_messages + block_messages, html):
                    logger.warning(f"{msg} exist! {url}")
                    self.close_driver()

                    # 指定された時間プロキシをブロック
                    self.proxy_manager.block(sleep_time)
                    continue

                if wait_for is not None:
                    try:
                        driver.wait_for_element(wait_for, timeout=30)
                    except Exception as e:
                        retry += 1
                        logger.error(f"wait_for_element: retry {retry}times {type(e)}: {str(e)}")
                        self.close_driver()
                        driver.sleep(random.uniform(5, 10))
                        if retry >= MAX_RETRY:
                            logger.error(
                                f"wait_for_element: retry {retry} times >= MAX_RETRY {type(e)}: {str(e)}"
                            )
                            return FetchpageResponse(
                                status_code=404,
                                text="",
                                ok=False,
                                driver=driver,
                            )
                        else:
                            continue

                for _ in range(5):
                    html = driver.get_page_source()
                    if html is None or html.strip() == "":
                        logger.warning(f"Page source is empty, retrying: {url}")
                        driver.refresh()
                        time.sleep(2)
                    else:
                        break

                return FetchpageResponse(
                    status_code=200,
                    text=html,
                    ok=True,
                    driver=driver,
                )

            except Exception as e:
                logger.error(f"{type(e)}: {str(e)}")
                self.close_driver()
                driver.sleep(random.uniform(5, 10))

    def scroll_to_line(self, line: int) -> None:
        driver = self.get_driver()

        SCROLL_PAUSE_TIME = 2  # ページがロードされるまでの待機時間（調整可能）

        for _ in range(5):
            # 1000ドットスクロール
            driver.execute_script("window.scrollBy(0, 1000);")

            self.close_popup()

            # ロード待ち
            time.sleep(SCROLL_PAUSE_TIME)

            # 新しい高さを取得
            new_height = driver.execute_script("return window.scrollY;")

            if new_height > line:
                # 指定したラインを越えたら終了
                break

            logger.info(f"new_height: {new_height}")

    def close_popup(self) -> None:
        if not self.popup_locator:
            return
        logger.info("close_popup (elf.popup_locator): %s", self.popup_locator)
        driver = self.get_driver()
        for ele in driver.find_elements(self.popup_locator):
            logger.info(f"close_popup: {ele}")
            try:
                ele.click()
            except Exception as e:
                logger.error(f"close_popup: {type(e)}: {str(e)}")
                pass

    @override
    def get_driver(self) -> Any:
        """
        ドライバを取得

        Returns:
            Any: SeleniumBaseのドライバ
        """
        if self.is_connected():
            return self.driver

        proxy = self.get_proxy()

        browser_args = {
            "uc": True,
            "locale_code": "en_US",
            "headless": False,
            "block_images": self.options.get("block_images", True),
            "page_load_strategy": "eager",
            "proxy": proxy,
        }
        if self.options.get("profile_path"):
            profile_path = Path(self.options.get("profile_path")).absolute()
            logger.info(f"profile_path: {profile_path}")
            browser_args["user_data_dir"] = str(profile_path)
            self.profile_path = profile_path

        # sb_settings.PAGE_LOAD_TIMEOUT = 30
        self.driver = Driver(**browser_args)
        self.driver.set_page_load_timeout(30)

        return self.driver

    @override
    def gen_proxy_url(self, proxy_url: str) -> str:
        """
        http://username:password@proxy_host:proxy_port 形式から
        username:password@proxy_host:proxy_port 形式に変換する

        Args:
            proxy_url (str): プロキシURL

        Returns:
            str: 生成されたプロキシURL
        """
        if m := re.match(r"http:\/\/(?P<proxy_url>\S+)$", proxy_url):
            proxy_url = m.group("proxy_url")
        else:
            proxy_url = f"{proxy_url}"

        return proxy_url

    @override
    def close_driver(self) -> None:
        """
        ドライバを閉じる
        """
        if self.is_connected():
            self.driver.quit()
            self.driver = None

        # プロファイルも削除する
        if self.profile_path and self.profile_path.is_dir():
            shutil.rmtree(self.profile_path)

    @override
    def is_connected(self) -> bool:
        if not hasattr(self, "driver"):
            self.driver = None
            return False

        if self.driver is None:
            return False

        try:
            self.driver.title
            return True
        except Exception:
            return False

    @override
    def random_action(self):
        """
        ランダムにページにアクセスします。

        Args:
            page (Page): ページオブジェクト。
            driver: SeleniumbaseのDriverオブジェクト。
        """
        driver = self.get_driver()
        driver.sleep(random.uniform(1, 3))
        driver.send_keys("//body", Keys.PAGE_DOWN)
