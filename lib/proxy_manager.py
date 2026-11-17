import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Literal

import requests
import sqlalchemy as sa

from voracity2 import settings
from voracity2.models.database import session
from voracity2.models.proxy import Proxy, Status

ProxyType = Literal["seleniumbase", "requests", "playwright"]

logger = settings.logger


class ProxyManager:
    """
    プロキシ管理クラス。プロキシの取得、ブロックを行います。
    """

    def __init__(self, group_name: str):
        self.group_name = group_name

    def get(self) -> str:
        """
        プロキシを取得します。
        """
        while True:
            try:
                proxy = (
                    session.query(Proxy)
                    .filter(
                        Proxy.group_name == self.group_name,
                        Proxy.status == Status.AVAILABLE,
                        Proxy.available_at <= datetime.now(),
                    )
                    .order_by(sa.func.random())
                    .first()
                )
                if not proxy:
                    session.commit()
                    logger.info("No proxy available wait 2 hours")
                    time.sleep(2 * 60 * 60)
                    continue

                self.proxy_id = proxy.id
                proxy_url = proxy.url
                session.commit()

                return proxy_url

            except Exception as e:
                logger.error(f"get proxy failed: {type(e)}:{str(e)} wait 60sec")
                session.rollback()

                time.sleep(60)
                continue

    def block(self, sleep_time: int = 60) -> None:
        proxy = session.get(Proxy, self.proxy_id)
        if proxy:
            proxy.block(sleep_time)

    def check(self, proxy_url: str) -> bool:
        for i in range(3):
            try:
                r = requests.get(
                    "http://www.msftncsi.com/ncsi.txt",
                    proxies={"http": proxy_url, "https": proxy_url},
                    timeout=5,
                )
                if r.ok:
                    return True
            except Exception as e:
                logger.error(f"check proxy failed #{i}: {type(e)} : {str(e)}")
                time.sleep(2)
        else:
            return False

    def check_all(self) -> None:
        """
        全てのプロキシをチェックします。
        """
        proxy_urls = (
            session.query(Proxy.url)
            .filter(Proxy.status == Status.AVAILABLE)
            .group_by(Proxy.url)
            .all()
        )
        blocked_urls: list[str] = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_param = {
                executor.submit(self.check, proxy_url[0]): proxy_url[0] for proxy_url in proxy_urls
            }

            for future in as_completed(future_to_param):
                proxy_url = future_to_param[future]
                if future.result():
                    logger.info(f"Proxy is available {proxy_url}")
                else:
                    logger.warning(f"Proxy is blocked {proxy_url}")
                    blocked_urls.append(proxy_url)

        for blocked_url in blocked_urls:
            logger.warning(f"Blocking proxy {blocked_url}")
            for proxy in session.query(Proxy).filter(Proxy.url == blocked_url):
                proxy.block(4 * 60 * 60)
