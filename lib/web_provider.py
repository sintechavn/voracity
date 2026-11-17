import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from voracity2.lib.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)


class FetchpageResponse(BaseModel):
    ok: bool = True
    status_code: int = 200
    message: str = ""
    text: str = ""
    driver: Any = None
    cookies: Any = None
    headers: dict = {}


class WebProvider(ABC):
    driver: Any = None
    proxy_manager: ProxyManager
    popup_locator: str | None = None
    proxy_url: str | None = None
    block_images: bool = False

    def __init__(self, options: dict = {}):
        """
        初期化メソッド。Playwrightのブラウザとコンテキストを設定
        """
        self.options = options
        self.block_images = self.options.get("block_images", True)
        self.proxy_manager = ProxyManager(group_name=options.get("proxy_group_name", "default"))

    @abstractmethod
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
    ) -> FetchpageResponse:
        """
        指定されたURLのページオブジェクトを取得します。
        Returns:
            FetchpageResponse: FetchpageResponseオブジェクト。
        """
        return FetchpageResponse()

    @abstractmethod
    def gen_proxy_url(self, proxy_url: str) -> str | dict:
        """
        プロキシURLを生成します。
        """
        pass

    @abstractmethod
    def get_driver(self) -> Any:
        """
        ドライバを取得します。
        """
        pass

    @abstractmethod
    def close_driver(self) -> None:
        """
        ドライバを閉じます。
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        ドライバが接続されているかどうかを確認します。
        """
        pass

    @abstractmethod
    def random_action(self) -> None:
        """
        ランダムなアクションを実行します。
        """
        pass

    def message_exists(self, block_messages: list[str], text: str) -> str | None:
        """
        ブロックメッセージが存在するかどうかを確認します。

        Args:
            text (str): ページのテキスト。

        Returns:
            str|None: ブロックメッセージが存在する場合はメッセージ、存在しない場合はNone。
        """
        for message in block_messages:
            if message in text:
                return message
        return None

    def get_proxy(
        self,
    ) -> str | dict | None:
        proxy: str = self.proxy_manager.get()
        self.proxy_url = proxy
        proxy_url: str | dict = self.gen_proxy_url(proxy)

        logger.info(f"proxy_url: {proxy_url}")

        return proxy_url

    def get_current_proxy(self) -> str | None:
        """
        現在使用しているプロキシを取得する

        Returns:
            str | None: 現在のプロキシURLまたはNone
        """
        return self.proxy_url
