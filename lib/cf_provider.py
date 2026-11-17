import logging
import multiprocessing as mp
import os
import random
import re
import time
from typing import Any, override
from urllib.parse import urlparse

import platformdirs
from pathlib import Path

import psutil
from browserforge.fingerprints import Screen
from camoufox.sync_api import Camoufox
from selenium.webdriver.common.keys import Keys

from voracity2.lib.web_provider import FetchpageResponse, WebProvider

logger = logging.getLogger(__name__)

MAX_RETRY: int = 3
PROFILE_MAX: int = 10
PROFILE_LOCK_TIMEOUT: int = 600  # 10分


class CFFetcher(mp.Process):
    driver: Any
    block_images: bool

    def __init__(self, pipe, proxy_url: str, block_images: bool):
        super().__init__()
        self.headers: dict = {}
        self.pipe = pipe
        self.proxy_url = proxy_url
        self.block_images = block_images
        self.driver = None
        self.using_profile_dir: Path | None = None
        logger.info(f"CFFetcher initialized. {self.proxy_url}, block_images: {self.block_images}")


    def request_handler(self, request):
        headers = request.all_headers()

        host = headers.pop("host") or urlparse(request.url).hostname
        self.headers[host] = headers

    def run(self):
        logger.info(f"PID:{os.getpid()} CFFetcher started")


        if not self.driver:
            self.driver = self.get_driver()
            page = self.driver.new_page()
            self.driver_pids = []
        while True:
            cmd, arg = self.pipe.recv()
            logger.info(f"Received command: {cmd}, with argument: {arg}")
            self.update_profile_lock()

            match cmd:
                case "pids":
                    self.pipe.send(self.driver_pids)

                case "open":
                    page.on("request", self.request_handler)
                    page.goto(arg, referer="https://www.google.com/", timeout=60000)
                    time.sleep(1)
                    self.pipe.send(page.content())

                case "get_headers":
                    cookies = page.context.cookies()
                    headers = self.headers
                    self.pipe.send((headers, cookies))

                case "refresh":
                    page.reload()
                    time.sleep(2)
                    self.pipe.send(page.content())

                case "fetch":
                    self.pipe.send(page.content())

                case "execute":
                    page.evaluate(arg)
                    self.pipe.send(("ok", None))

                case "wait_for":
                    try:
                        page.locator(arg).first.wait_for()
                        self.pipe.send(("ok", None))
                    except Exception as e:
                        self.pipe.send(("error", str(e)))

                case "close":
                    self.driver.close()
                    self.pipe.send(("ok", None))
                    break

    def get_driver(self):
        parsed_proxy = urlparse("http://" + self.proxy_url)
        proxy_dict = {
            "server": f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}",
            "username": parsed_proxy.username,
            "password": parsed_proxy.password,
        }
        logger.info(f"Using proxy: {proxy_dict}")

        user_data_dir = self.get_profile_dir()

        browser_args = {
            "headless": False,
            "proxy": proxy_dict,
            "screen": Screen(max_width=1920, max_height=1080, min_width=1600, min_height=900),
            "os": ["windows", "macos", "linux"],
            "locale": "en-US",
            "geoip": False,
            "persistent_context": True,
            "user_data_dir": user_data_dir,
        }

        logger.info(f"Starting Driver with args: {browser_args}")

        driver = Camoufox(**browser_args).start()

        return driver
    
    def get_profile_dir(self)->Path:
        user_data_root:Path = Path(platformdirs.user_data_dir(appname="voracity2", appauthor="handc")) / "user_data"
        for profile_dir_no in range(1,PROFILE_MAX+1):
            user_data_dir = user_data_root / f"cf{profile_dir_no}"
            in_use_file = user_data_root / f"cf{profile_dir_no}.lock"
            if user_data_dir.exists():
                if in_use_file.exists() and time.time() - in_use_file.stat().st_mtime < PROFILE_LOCK_TIMEOUT:
                    logger.info(f"Profile directory in use: {user_data_dir}")
                    continue
                else:
                    logger.info(f"Using profile directory: {user_data_dir}")
                    self.using_profile_dir = user_data_dir
                    self.update_profile_lock()
                    return user_data_dir
            else:
                user_data_dir.mkdir(parents=True, exist_ok=True)
                in_use_file.touch()
                logger.info(f"Created and using profile directory: {user_data_dir}")
                return user_data_dir
        else:
            raise Exception("No available profile directories.")
        
    def update_profile_lock(self):
        if self.using_profile_dir is not None:
            in_use_file = self.using_profile_dir.with_suffix(".lock")
            if in_use_file.exists():
                in_use_file.touch()
                logger.info(f"Updated lock file timestamp: {in_use_file}")
                return


class CFProvider(WebProvider):
    popup_loator: str | None = None
    fetcher: CFFetcher | None = None
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
            self.fetcher = CFFetcher(
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
            logger.info(f"set startup pages {startup_pages}")
            self.startup_pages = startup_pages.copy()

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
                        scroll_to_line=scroll_to_line,
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

                # 成功時のレスポンス
                time.sleep(random.uniform(2, 5))
                self.parent_pipe.send(("get_headers", None))
                self.parent_pipe.poll(30)
                headers, cookies = self.parent_pipe.recv()
                return FetchpageResponse(
                    status_code=200,
                    text=html,
                    ok=True,
                    driver=None,
                    headers=headers,
                    cookies=cookies,
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
