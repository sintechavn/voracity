import logging
import random
import time
from typing import override

import curl_cffi

from voracity2.lib.web_provider import FetchpageResponse, WebProvider

logger = logging.getLogger(__name__)


class CCProvider(WebProvider):
    """
    curl_cffiを使用してHTTPリクエストを行うプロバイダクラス。"""

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
            Page | None: ページオブジェクトまたはNone。
        """

        while True:
            try:
                proxies = self.get_proxy()
                headers.pop("user-agent", None)
                r = curl_cffi.get(
                    url,
                    proxies=proxies,
                    cookies=cookies,
                    headers=headers,
                    # impersonate=random.choice(["safari", "chrome", "firefox"]),
                    impersonate="chrome136",
                    timeout=10,
                    verify=False,
                    http_version=curl_cffi.CurlHttpVersion.V1_1,
                )

                if (r.status_code in not_found_status) or self.message_exists(
                    not_found_messages, r.text
                ):
                    logger.warning(f"Page not found! {r.status_code} {url}")
                    return FetchpageResponse(
                        status_code=404,
                        text=r.text,
                        ok=False,
                        driver=None,
                    )

                blocked = True
                if self.options.get("proxy_block_flg") is False:
                    blocked = False
                elif r.status_code in block_status:
                    logger.warning(
                        f"blocked by status_code {r.status_code}. sleep {sleep_time} sec:{self.get_current_proxy()}:{url}"
                    )
                elif ret := self.message_exists(block_messages, r.text):
                    logger.warning(
                        f"blocked by message {ret}. sleep {sleep_time} sec:{self.get_current_proxy()}:{url}"
                    )
                else:
                    blocked = False

                if blocked:
                    # 指定された時間プロキシをブロック
                    self.proxy_manager.block(sleep_time)
                    continue

                if r.status_code >= 300:
                    time.sleep(3)
                    continue

                return FetchpageResponse(
                    status_code=r.status_code,
                    text=r.text,
                    ok=True,
                    driver=None,
                )
            except Exception as e:
                logger.error(f"{type(e)}: {str(e)}")
                self.close_driver()
                time.sleep(random.uniform(5, 10))

    @override
    def get_driver(self) -> None:
        """
        ドライバを取得します。
        """
        return None

    @override
    def close_driver(self) -> None:
        """
        ドライバを閉じます。
        """
        pass

    @override
    def gen_proxy_url(self, proxy_url):
        return {"http": proxy_url, "https": proxy_url}

    def is_connected(self):
        return True

    def random_action(self) -> None:
        pass
