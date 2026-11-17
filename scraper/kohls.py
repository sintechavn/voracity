import json
import logging
import math
import random
import re
import time
from collections.abc import Generator
from datetime import datetime
from itertools import groupby

import bs4
import parsel

from voracity2.lib.cf_provider import CFProvider
from voracity2.lib.utils import ResultDict, ResultList, Status
from voracity2.lib.web_provider import FetchpageResponse
from voracity2.models.category import Category
from voracity2.models.item import Item
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class KohlsScraper(BaseScraper):
    site_id: int = 33
    site_name: str = "kohls"
    domain = "www.kohls.com"
    not_found_messages = ["We couldn't find a match"]
    block_messages = ["Access Denied"]

    page_wait_for = '//div[@id="productsHeading"]'

    page2_wait_for: str = '//img[@title="Next Page"] | //button[@aria-label="Next Page"]'
    page2_scroll_to_bottom = False
    item_locator = '//div[contains(@class,"prod_img_block")]/a | //a[@data-dte="product-title"]'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=CFProvider(options=options))

    def get_max_page_no(self, html: str) -> int | None:
        parser = parsel.Selector(html)
        max_page = parser.xpath('//div[@id="productsHeading"]/span/text()').getall()
        if not max_page:
            return None

        max_page_no: int = math.ceil(int(max_page[1].replace(",", "")) / 120)

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> Category:
        # return f"{category_url}&page={page_no}"

        page_no -= 1

        _url = re.sub(r"WS=\d+", "", category_url)
        if page_no == 0:
            url = self.get_abs_url(_url)
        else:
            url = self.get_abs_url(f"{_url}&WS={page_no * 48}")

        return url

    def get_sku(self, page_: Page_, item_url: str) -> str:
        """
        SKUを取得します。

        Args:
            page_ (Page_): ページオブジェクト。
            item_url (str): アイテムのURL。

        Returns:
            str: SKU。
        """
        if m := re.match(r".+/product/prd-(.+)/", item_url):
            sku = m.group(1)
        else:
            sku = item_url

        return sku

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
                    # cookies={c["name"]: c["value"] for c in res.cookies},
                    # headers=res.headers.get("www.kohls.com", {}),
                    block_status=self.block_status,
                    not_found_messages=self.not_found_messages,
                    block_messages=self.block_messages,
                    startup_pages=[
                        "https://www.google.com",
                        "https://www.kohls.com/",
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
        soup = self.create_soup(html)
        ret = self.get_common_data(soup)
        if ret.code != Status.END_OK:
            return ret.message

        common_data = ret.data.copy()
        common_data.update(
            {
                "site_id": self.site_id,
                "page_id": page_.id,
                "status": Status.END_OK,
                "url": page_.url,
                "updated_at": datetime.now(),
                "updated_by": self.hostname,
            }
        )

        ret = self.get_variant_data(soup)
        if ret.code != Status.END_OK:
            return ret.message

        variant_data = ret.data.copy()
        records = self.create_records(common_data, variant_data)

        for record in records:
            yield record

    def create_soup(self, html: str) -> bs4.BeautifulSoup:
        soup = bs4.BeautifulSoup(html, "lxml")
        return soup

    def get_common_data(self, soup) -> ResultDict:
        breadcrumb = [a.text.strip() for a in soup.select(".bread-crupms a") if a.text.strip()][1:]

        gender = next(
            (g for g in ["womens", "mens"] if any(g in crumb.lower() for crumb in breadcrumb)), None
        )

        try:
            brand: str = soup.select_one(".sub-product-title").text.strip()
        except Exception:
            brand: str = ""

        common_data = {
            "name": soup.select_one(".product-title").text.strip(),
            "brand": brand,
            "site_id": self.site_id,
            "currency": "USD",
            "gender": gender,
        }

        common_data = self.insert_categories(common_data, breadcrumb)

        images = soup.select("div.pdp-large-alt-images > div > img")
        image_urls = [img["src"].split("?")[0] for img in images]

        common_data = self.insert_images(common_data, image_urls, start_index=2)

        return ResultDict(code=Status.END_OK, message="OK", data=common_data)

    def get_variant_data(self, soup) -> ResultList:
        variant_data = []
        scripts = soup.select("script")
        script = [script.text for script in scripts if "var productV2JsonData" in script.text]
        if len(script) == 0:
            return ResultList(code=Status.END_ERROR, message="script not found#")

        if m := re.search(r"var productV2JsonData = (.*);", script[0]):
            product_json = m.group(1)
        else:
            return ResultList(code=Status.END_ERROR, message="prodcutV2JsonData not found")

        product = json.loads(product_json)

        sku_code = product["webID"]

        skus = [sku for sku in product["SKUS"] if sku["availability"] != "Out of Stock"]
        if len(skus) == 0:
            return ResultList(code=Status.END_ERROR, message="no available skus")

        skus_sorted = sorted(skus, key=lambda x: x["color"])

        variant_data = []
        for color, group in groupby(skus_sorted, key=lambda x: x["color"]):
            group_list = list(group)
            sizes = [sku_["size"] for sku_ in group_list]
            price = [sku_["price"] for sku_ in group_list][0]

            regular_price = price["regularPrice"]["minPrice"]
            sale_price = price["yourPriceInfo"]["yourPrice"]

            if sale_price is None:
                sale_price = price["salePrice"]
                if sale_price is None:
                    sale_price = regular_price
                else:
                    sale_price = price["salePrice"]["minPrice"]

            variant_data.append(
                {
                    "size": self.join_sizes(sizes),
                    "key": f"{sku_code}#{color}",
                    "color": color,
                    "sku": sku_code,
                    "product_code": sku_code,
                    "product_code2": next(
                        (sku_["skuCode"] for sku_ in skus_sorted if sku_["color"] == color), None
                    ),
                    "image1": next(
                        (
                            sku_["images"][0]["url"].split("?")[0]
                            for sku_ in skus_sorted
                            if sku_["color"] == color
                        ),
                        None,
                    ),
                    "price": regular_price,
                    "sale_price": sale_price,
                }
            )

        return ResultList(code=Status.END_OK, message="OK", data=variant_data)

    def join_sizes(self, sizes) -> str:
        if None in sizes:
            return "サイズ One-Size"
        parsed_sizes = [re.sub(r" ", "-", size) for size in sizes]
        size_str = " ".join(parsed_sizes)
        return "サイズ " + size_str
