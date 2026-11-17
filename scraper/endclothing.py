import json
import logging
import random
import re
from collections.abc import Generator
from datetime import datetime
import time

import lxml.html
import parsel

from voracity2.lib.cf_provider import CFProvider
from voracity2.lib.utils import ResultDict, Status
from voracity2.models.category import Category
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper
from voracity2.models.item import Item
from voracity2.lib.web_provider import FetchpageResponse

logger = logging.getLogger(__name__)


class EndclothingScraper(BaseScraper):
    site_id: int = 35
    site_name: str = "endclothing"
    domain = "www.endclothing.com"
    block_messages = [
        "Something Went Wrong",
        "Access Denied",
        "Sorry, You have been blocked.",
    ]

    page_wait_for = '//span[@data-test-id="product-count-nbHits"]'
    item_locator = '//a[@data-test-id="ProductCard__ProductCardSC"]'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=CFProvider(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        item_count = parser.xpath(f"{self.page_wait_for}/text()").getall()[-1]
        max_page_no = int(int(item_count) / 120) + 1

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> Category:
        base_url = category_url.split("?")[0]

        return f"{base_url}?page={page_no}"

    def get_sku(self, page_: Page_, item_url: str) -> str:
        if "?" in item_url:
            return item_url.split("?")[0]
        else:
            return item_url

    def get_itemurl(self, url):
        url = super().get_itemurl(url)
        url = url.split("?")[0]

        return url

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
                    block_status=self.block_status,
                    not_found_messages=self.not_found_messages,
                    block_messages=self.block_messages,
                    startup_pages=[
                        "https://www.endclothing.com/jp",
                        "https://www.endclothing.com/jp/clothing",
                    ],
                )
                if response.status_code == 404:
                    self.update_status(page_, Status.END_ERROR, "Page not found")
                    continue
                items: list[dict] = [i for i in self.parse_item(page_, response.text)]
                self.save_data(items, Item)
                self.update_status(page_, Status.END_OK, "OK")
                time.sleep(random.uniform(5, 10))
            except Exception as e:
                logger.error(f"{type(e)}: {str(e)}")
                self.update_status(page_, Status.END_ERROR, str(e))

        self.end_crawl()

    def parse_item(self, page_: Page_, html: str) -> Generator[dict, None, str]:
        base_data = {
            "site_id": self.site_id,
            "page_id": page_.id,
            "status": Status.END_OK,
            "result_text": "OK",
            "currency": "JPY",
            "url": page_.url,
            "updated_at": datetime.now(),
            "updated_by": self.hostname,
        }

        parser = lxml.html.fromstring(html)
        # gender = (
        #     "Women" if "women" in parser.xpath('//a[contains(@class,"Logo")]/@href')[0] else "Men"
        # )
        product_data: dict = json.loads(parser.xpath('//script[@id="__NEXT_DATA__"]/text()')[0])
        initial_props = product_data["props"]["initialState"]["misc"]
        if initial_props == {}:
            return "No initial props found"

        ret = self.get_common_data(product_data)
        if ret.code != Status.END_OK:
            return ret.message

        yield base_data | ret.data  # | {"gender": gender}

    def get_common_data(self, product_data: dict):
        initial_props = product_data["props"]["initialState"]["misc"]
        product_data = product_data["props"]["initialProps"]["pageProps"]["product"]
        if not product_data["in_stock"]:
            return ResultDict(code=Status.END_ERROR, message="在庫なし")
        categories = [category["title"] for category in initial_props["breadcrumb"]["crumbs"]]
        categories.pop(-1)
        images = [image["file"] for image in product_data["media_gallery_entries"]]
        sizes = [
            option["values"] for option in product_data["options"] if option["label"] == "Size"
        ][0]
        exist_sizes = [re.sub(" ", "-", size["label"]) for size in sizes if size["in_stock"]]
        size_str = "サイズ " + " ".join(exist_sizes)
        if "special_price" in product_data:
            sale_price = product_data["special_price"]
        else:
            sale_price = None
        sku = product_data["sku"]
        common_data = {
            "name": product_data["name"],
            "currency": "USD",
            "product_code": sku,
            "product_code2": product_data["id"],
            "sku": sku,
            "key": f"{sku}#{product_data['colour']}",
            "brand": product_data["brand"],
            "color": product_data["colour"],
            "price": product_data["price"],
            "sale_price": sale_price,
            "size": size_str,
            "gender": categories[0] if categories[0] in ("Womens", "Mens") else "Unisex",
        }
        common_data = self.insert_images(common_data, images, 1)
        common_data = self.insert_categories(common_data, categories)
        return ResultDict(code=Status.END_OK, message="OK", data=common_data)

    def get_json(self, soup, key_string):
        product_json = soup.select_one(key_string).text
        return json.loads(product_json)

    def get_gender(self, category_url: str) -> str:
        if "women" in category_url:
            gender = "Women"
        else:
            gender = "Men"
        return gender
