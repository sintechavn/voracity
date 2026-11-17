import json
import re
import urllib
from collections.abc import Generator
from datetime import datetime

import bs4
import parsel

from voracity2.lib.sb_provider import SBProvider
from voracity2.lib.utils import Status
from voracity2.models.category import Category
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper


class BcScraper(BaseScraper):
    site_id: int = 37
    site_name: str = "bc"
    domain = "www.backcountry.com"
    block_messages = ["Backcountry is not available"]
    item_locator = '//div[@data-id="PLI"]//a'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=SBProvider(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        max_page = parser.xpath('//a[@data-id="pageItem"][last()]/text()').get()
        if not max_page:
            max_page_no: int = 1
        else:
            max_page_no: int = int(max_page)

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> Category:
        base_url = category_url.split("?")[0]

        if page_no == 1:
            return f"{base_url}?sort=newest"
        else:
            return f"{base_url}?page={page_no}&sort=newest"

    def get_sku(self, page_: Page_, item_url: str) -> str:
        if "?" in item_url:
            return item_url.split("?")[0]
        else:
            return item_url

    def parse_item(self, page_: Page_, html: str) -> Generator[dict, None, str]:
        parser = parsel.Selector(html)
        elem = parser.xpath('//script[@id="__NEXT_DATA__"]/text()').get()
        if not elem:
            return "No JSON data"

        common_json = json.loads(elem)

        common_data = {}
        common_data = self.get_common_data(common_json)
        variant_data = self.get_variant_data(common_json)
        if len(variant_data) == 0:
            return "No variant data found"

        for record in self.create_records(common_data, variant_data):
            record.update(
                {
                    "site_id": self.site_id,
                    "page_id": page_.id,
                    "status": Status.END_OK,
                    "url": page_.url,
                    "updated_at": datetime.now(),
                    "updated_by": self.hostname,
                    "key": f"{record['product_code']}#{record['color']}",
                }
            )

            yield record

    def get_common_data(self, common_json):
        product = common_json["props"]["pageProps"]["product"]
        categories = [category["name"] for category in product["breadcrumbs"]]
        images = [
            urllib.parse.urljoin("https://www.backcountry.com/", image["twelveHundredImg"])
            for image in product["detailImages"]
        ]
        common_data = {
            "name": product["title"],
            "site_id": self.site_id,
            "brand": product["brand"]["name"],
            "currency": "USD",
        }
        common_data = self.insert_images(common_data, images, 2)
        common_data = self.insert_categories(common_data, categories)
        return common_data

    def get_variant_data(self, json):
        product = json["props"]["pageProps"]["product"]
        skus = product["skus"]
        color_variation = product["colorsCollection"]
        variant_data = []
        append = variant_data.append
        for color in color_variation.values():
            sizes = color["sizes"]
            for size in sizes.values():
                sku = size["sku"]
            for sku_dictionary in skus:
                if sku_dictionary["id"] == sku:
                    sale_price = sku_dictionary["salePrice"]
                    standard_price = sku_dictionary["listPrice"]
                    break
            if sale_price == standard_price:
                sale_price = None
            sku = "02-" + re.sub(r"(^.*)-.*$", r"\1", sku)
            sizes = sizes.keys()
            sizes = [re.sub(r" ", "-", size) for size in sizes]
            size_str = "サイズ " + " ".join(sizes)
            variation = {
                "color": color["name"],
                "image1": urllib.parse.urljoin(
                    "https://www.backcountry.com/", color["twelveHundredImg"]
                ),
                "size": size_str,
                "sale_price": sale_price,
                "price": standard_price,
                "sku": sku,
                "product_code": sku,
            }
            append(variation)
        return variant_data

    def get_json(self, soup, key_string):
        json_obj = soup.select_one(key_string)
        product_json = re.findall(r"{.*}", str(json_obj))[0]
        return json.loads(product_json)

    def create_soup(self, html: str) -> bs4.BeautifulSoup:
        soup = bs4.BeautifulSoup(html, "lxml")
        return soup
