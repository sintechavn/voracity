import logging
import multiprocessing as mp
import os
import random
import re
import time
from typing import Any, override

import psutil
from selenium.webdriver.common.keys import Keys
from seleniumbase import Driver

from voracity2.lib.web_provider import FetchpageResponse, WebProvider

logger = logging.getLogger(__name__)

MAX_RETRY: int = 3


class SBFetcher(mp.Process):
    driver: Any
    block_iomages: bool

    def __init__(self, pipe, proxy_url: str, block_images: bool):
        super().__init__()
        self.pipe = pipe
        self.proxy_url = proxy_url
        self.block_images = block_images
        self.driver = None
        logger.info(f"SBFetcher initialized. {self.proxy_url}, block_images: {self.block_images}")

    def run(self):
        logger.info(f"PID:{os.getpid()} SBFetcher started")
        if not self.driver:
            self.driver = self.get_driver()
            self.driver_pids = [self.driver.service.process.pid, self.driver.browser_pid]
            # self.driver_pids = [self.driver.service.process.pid]
        while True:
            cmd, arg = self.pipe.recv()
            logger.info(f"Received command: {cmd}, with argument: {arg}")

            match cmd:
                case "pids":
                    self.pipe.send(self.driver_pids)

                case "open":
                    self.driver.open(arg)
                    time.sleep(1)
                    self.pipe.send(self.driver.get_page_source())

                case "refresh":
                    self.driver.refresh()
                    time.sleep(2)
                    self.pipe.send(self.driver.get_page_source())

                case "fetch":
                    self.pipe.send(self.driver.get_page_source())

                case "execute":
                    self.driver.execute_script(arg)
                    self.pipe.send(("ok", None))

                case "wait_for":
                    try:
                        self.driver.wait_for_element(arg, timeout=30)
                        self.pipe.send(("ok", None))
                    except Exception as e:
                        self.pipe.send(("error", str(e)))

                case "close":
                    self.driver.quit()
                    for pid in self.driver_pids:
                        try:
                            os.kill(pid, 9)
                        except Exception:
                            pass
                    self.pipe.send(("ok", None))
                    break

    def get_driver(self):
        browser_args = {
            "uc": True,
            "locale_code": "en",
            "headless": False,
            "block_images": self.block_images,
            "page_load_strategy": "eager",
            "proxy": self.proxy_url,
        }
        logger.info(f"Starting Driver with args: {browser_args}")

        driver = Driver(**browser_args)

        return driver


class SBProvider2(WebProvider):
    popup_loator: str | None = None
    fetcher: SBFetcher | None = None
    parent_pipe = None
    pids: list[int] = []
    startup_pages: list[str] = []

    default_block_messages = [
        "Access Denied",
        "Something Went Wrong",
        "ERR_TIMED_OUT",
        "ERR_TOO_MANY_RETRIES",
        "ERR_TUNNLE_CONNECTION_FAILED",
        "ERR_PROXY_CONNECTION_FAILED",
        "ERR_HTTP2_PROTOCOL_ERROR",
        "This site can't be reached",
        "Bad Gateway",
        "このサイトにアクセスできません",
        "インターネットに接続されていません",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fetcher = None
        self.parent_pipe = None
        self.pids = []
        self.fetcher_started = False

    def _ensure_fetcher(self) -> bool:
        """フェッチャープロセスが動作していることを確認し、必要に応じて開始"""
        if self.fetcher is None or not self.fetcher.is_alive():
            if self.fetcher is not None:
                self.terminate_fetcher()

            self.parent_pipe, child_pipe = mp.Pipe()
            self.fetcher = SBFetcher(
                child_pipe,
                self.get_proxy(),
                self.block_images,
            )
            self.fetcher.start()
            self.fetcher_started = True

            # プロセスIDを取得
            try:
                self.parent_pipe.send(("pids", None))
                if self.parent_pipe.poll(60):
                    self.pids = self.parent_pipe.recv()
                    logger.info(f"Fetcher process started with PIDs: {self.pids}")
                    return True
                else:
                    logger.error("Fetcher process failed to start.")
                    self.terminate_fetcher()
                    return False
            except Exception as e:
                logger.error(f"Failed to communicate with fetcher: {e}")
                self.terminate_fetcher()
                return False

        else:
            self.fetcher_started = False

        return True

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
        startup_pages: list[str] = [],
        fetch_startup_pages: bool = True,
    ) -> FetchpageResponse:
        """
        指定されたURLのページオブジェクトを取得します。

        Args:
            url (str): ページのURL。

        Returns:
            GetpageResponse | None: GetpageResponseオブジェクトまたはNone。
        """
        logger.info(f"fetch_page: {url}")

        retry: int = 0
        self.popup_locator = popup_locator
        if startup_pages:
            self.startup_pages = startup_pages.copy()
            logger.info(f"set startup pages {self.startup_pages}")

        while True:
            # フェッチャープロセスを確実に開始
            if not self._ensure_fetcher():
                logger.error("Failed to start fetcher process")
                self.proxy_manager.block(sleep_time)
                continue

            if self.fetcher_started and fetch_startup_pages:
                logger.info(f"{self.fetcher_started}, {self.startup_pages}")
                for startup_page in self.startup_pages:
                    self.fetch_page(
                        url=startup_page,
                        sleep_time=sleep_time,
                        headers=headers,
                        cookies=cookies,
                        referer=referer,
                        user_agent=user_agent,
                        not_found_status=not_found_status,
                        not_found_messages=not_found_messages,
                        block_status=block_status,
                        block_messages=block_messages,
                        fetch_startup_pages=False,
                    )
                # すべてのスタートアップページが処理された後、フラグをリセット
                self.fetcher_started = False

            try:
                # URLを開いてコンテンツを取得する
                self.parent_pipe.send(("open", url))
                if self.parent_pipe.poll(60):
                    html = self.parent_pipe.recv()
                else:
                    logger.warning(f"Page load time exceeded 60 seconds: {url}")
                    self.proxy_manager.block(sleep_time)
                    self.terminate_fetcher()
                    continue

                for _ in range(3):
                    if html is None or html.strip() == "":
                        logger.warning(f"Page source is empty, retrying: {url}")
                        self.parent_pipe.send(("refresh", None))
                        if self.parent_pipe.poll(30):
                            html = self.parent_pipe.recv()
                            break
                        else:
                            self.terminate_fetcher()
                            continue

                if msg := self.message_exists(not_found_messages, html):
                    logger.warning(f"{msg} exist! page not found!")
                    return FetchpageResponse(
                        status_code=404,
                        text=html,
                        ok=False,
                        driver=None,
                    )

                if msg := self.message_exists(self.default_block_messages + block_messages, html):
                    logger.warning(f"{msg} exist! {url}")
                    # 指定された時間プロキシをブロック
                    self.proxy_manager.block(sleep_time)
                    self.terminate_fetcher()
                    continue

                if wait_for is not None:
                    self.parent_pipe.send(("wait_for", wait_for))
                    if self.parent_pipe.poll(60):
                        status, err = self.parent_pipe.recv()
                        if status != "ok":
                            retry += 1
                            logger.error(f"wait_for_element: retry {retry}times {err}")
                            time.sleep(random.uniform(5, 10))
                            if retry >= MAX_RETRY:
                                logger.error(
                                    f"wait_for_element: retry {retry} times >= MAX_RETRY {err}"
                                )
                                return FetchpageResponse(
                                    status_code=404,
                                    text="",
                                    ok=False,
                                    driver=None,
                                )
                            self.terminate_fetcher()
                            continue

                time.sleep(random.uniform(2, 5))

                # 成功時のレスポンス
                return FetchpageResponse(
                    status_code=200,
                    text=html,
                    ok=True,
                    driver=None,
                )

            except (BrokenPipeError, EOFError, Exception) as e:
                logger.error(f"Communication error with fetcher: {e}")
                self.terminate_fetcher()
                continue

    def terminate_fetcher(self):
        """フェッチャープロセスを終了"""
        if self.fetcher is not None:
            try:
                if self.parent_pipe is not None:
                    self.parent_pipe.send(("close", None))
                    if self.parent_pipe.poll(5):
                        self.parent_pipe.recv()  # 応答を受信
            except Exception:
                pass

            try:
                proc = psutil.Process(self.fetcher.pid)
                for c in proc.children(recursive=True):
                    c.kill()
            except Exception:
                pass

            for pid in self.pids:
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass

            if self.fetcher.is_alive():
                self.fetcher.join(timeout=5)
                if self.fetcher.is_alive():
                    self.fetcher.kill()

            self.fetcher = None

        if self.parent_pipe is not None:
            try:
                self.parent_pipe.close()
            except Exception:
                pass
            self.parent_pipe = None

        self.pids = []

    def __del__(self):
        """デストラクタでリソースをクリーンアップ"""
        self.terminate_fetcher()

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
        pass

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
