import logging
import re

import parsel

from voracity2.models.category import Category
from voracity2.scraper.base_page import BasePageScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class YooxPageScraper(BasePageScraper):
    site_id: int = 31
    domain = "yoox.com"

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        stats_text = parser.xpath('//span[contains(@class, "Stats_totalHits")]/text()').get()
        if int(stats_text.replace("+", "")) < 60:
            max_page_no = 1
        else:
            pagination = parser.xpath('string(//li[@class="paginationPageCount"]/span)').extract()

            if len(pagination) >= 1 and (m := re.match(r"Page\s+\d+\s+of\s+(\d+)", pagination[0])):
                max_page_no = int(m.group(1))

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> Category:
        return f"{category_url}&page={page_no}"
