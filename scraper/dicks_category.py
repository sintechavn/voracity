import logging
import time
from collections.abc import Generator

import parsel

from voracity2.models.category import Category
from voracity2.scraper.base_category import BaseCategoryScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DicksCategoryScraper(BaseCategoryScraper):
    site_id: int = 34
    domain: str = "www.dickssportinggoods.com"
    browser_args: dict = {
        "args": [
            "--disable-features=Translate",
            "--start-maximized",
        ]
    }
    context_args: dict = {
        "permissions": [
            "geolocation",
        ],
        "proxy": {"server": "http://handc-c1:8080"},
    }
    max_page_locator: str = '//button[contains(@class,"bottom-pagination-number")]/span'

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        max_page_no = parser.xpath(f"{self.max_page_locator}/text()").getall()[-1]
        if max_page_no:
            return int(max_page_no)
        else:
            return 1

    def get_listpage_url(self, category_url, page_no) -> Category:
        base_url = category_url.split("?")[0]
        if page_no == 1:
            return f"{base_url}?selectedSort=6"
        else:
            return f"{base_url}?selectedSort=6&pageNumber={page_no-1}"

    def get_next(self) -> Generator[str, None, None]:
        prpage = self.get_context().new_page()
        prpage.goto("https://www.dickssportinggoods.com/")

        locator_text = "a.desktop-nav-container__nav--list-item"
        prpage.wait_for_selector(locator_text)

        f_list = []

        for loc in prpage.locator(locator_text).all():
            loc.click()
            time.sleep(1)

            parser = parsel.Selector(prpage.content())
            for idx, href in enumerate(
                parser.xpath('//a[contains(@class, "sublinks") and contains(@href,"/f/")]/@href')
            ):
                f_list.append(href.get())

        prpage.close()

        f_list = set(f_list)

        logger.info(f"Found {len(f_list)} categories.")

        for f in f_list:
            yield dict(
                site_id=self.site_id,
                url=f"https://{self.domain}{f}",
            )


def main():
    scraper = DicksCategoryScraper()
    scraper.crawl()


main()
