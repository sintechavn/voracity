import json
import logging
import math
import re
from collections.abc import Generator
from datetime import datetime
from itertools import groupby

import parsel

from voracity2.lib.sb_provider import SBProvider
from voracity2.lib.utils import ResultDict, Status
from voracity2.models.category import Category
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class SierraScraper(BaseScraper):
    site_id: int = 42
    site_name: str = "sierra"
    domain = "www.sierra.com"
    block_messages = ["Access Denied", "Content Protection"]

    page_wait_for = '//a[@aria-label="Go to Last Page"]'
    item_locator = '//div[@class="productCard-title-name"]/a'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=SBProvider(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        page_text = parser.xpath(f"{self.page_wait_for}/text()").getall()[-1]
        max_page_no = math.ceil(int(page_text.strip("page ")) / 4)

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> Category:
        base_url = category_url.split("?")[0]

        return f"{base_url}{page_no}/?perPage=96"

    def get_sku(self, page_: Page_, item_url: str) -> str:
        if "?" in item_url:
            return item_url.split("/")[1]
        else:
            return item_url

    def get_itemurl(self, url):
        url = super().get_itemurl(url)
        url = url.split("?")[0]

        return url

    def parse_item(self, page_: Page_, html: str) -> Generator[dict, None, str]:
        base_data = {
            "site_id": self.site_id,
            "page_id": page_.id,
            "status": Status.END_OK,
            "result_text": "OK",
            "currency": "USD",
            "url": page_.url,
            "updated_at": datetime.now(),
            "updated_by": self.hostname,
        }

        soup = self.create_soup(html)
        common_data = self.get_common_data(soup)
        if common_data.code != Status.END_OK:
            return common_data.message

        variant_data = self.get_variant_data(soup)
        if not variant_data:
            return ResultDict(code=Status.END_ERROR, message="バリアント情報が見つかりません")

        for record in self.create_records(common_data.data, variant_data):
            yield base_data | record | {"key": f"{record.get('sku')}#{record.get('color')}"}

    def get_common_data(self, soup, *args) -> dict:
        name = self.get_name(soup)
        brand = self.get_brand(soup)
        site_id = self.get_site_id()
        currency = self.get_currency()
        product_code = self.get_product_code(soup)
        breadcrumbs = self.get_breadcrumbs(soup)
        gender = self.get_gender(soup)

        image_urls = self.extract_image_urls(soup)
        sub_image_urls = image_urls[1:]

        sub_image_urls = [url.replace("~60", "~1080") for url in sub_image_urls]

        common_data = {
            "name": name,
            "brand": brand,
            "site_id": site_id,
            "currency": currency,
            "product_code": product_code,
            "sku": product_code,
            "gender": gender,
        }

        common_data = self.insert_images(common_data, sub_image_urls, start_index=2)

        common_data = self.insert_categories(common_data, breadcrumbs)

        return ResultDict(code=Status.END_OK, message="OK", data=common_data)

    def get_variant_data(self, soup, *args) -> list:
        # ctx = MiniRacer()
        # script = soup.select_one("#taffyDb > script").text + "JSON.stringify(skus);"
        # skus = ctx.eval(script)

        color_properties = self.extract_color_properties(soup)
        size_and_color_dict = self.parse_size_and_color_script(soup)

        variant_data = self.group_variants(size_and_color_dict, color_properties)
        return variant_data

    def get_name(self, soup):
        name_element = soup.select_one("h1.productTitle")
        if name_element is None:
            logger.error("Product name element not found")
            raise ValueError("Product name element not found")
        name = name_element.text.strip()
        return name

    def get_brand(self, soup):
        brand_element = soup.select_one("h1.productTitle > a")
        if brand_element is None:
            logger.error("Brand element not found")
            raise ValueError("Brand element not found")
        brand = brand_element.text.strip()
        return brand

    def get_site_id(self):
        site_id = self.site_id
        return site_id

    def get_currency(self):
        currency = "USD"
        return currency

    def get_product_code(self, soup):
        product_code_element = soup.select_one(".itemNo")
        if product_code_element is None:
            logger.error("Product code element not found")
            raise ValueError("Product code element not found")
        product_code_full = product_code_element.text.strip()
        product_code = product_code_full.split("#")[1].strip()
        self.product_code = product_code
        return product_code

    def get_breadcrumbs(self, soup):
        breadcrumbs = [a.text.strip() for a in soup.select(".breadcrumbs-item > a")]
        return breadcrumbs

    def extract_color_properties(self, soup):
        return {
            re.search(r"\((\d+)\)", color_chip["title"]).group(1): re.search(
                r"^(.*?)\s*\(", color_chip["title"]
            )
            .group(1)
            .strip()
            for color_chip in soup.select("a.colorChipSelectionBox")
        }

    def extract_image_urls(self, soup):
        self.main_image = soup.select_one("div.primaryImageContainer a img")["src"]
        logger.debug(f"Main image: {self.main_image}")
        images = soup.select("div.primaryImageContainer + div a > img")
        return [img["src"] for img in images]

    def parse_size_and_color_script(self, soup):
        size_and_color = soup.select_one("#taffyDb > script").text
        json_str = re.findall(r"\[.*?\]", size_and_color, re.DOTALL)[0]
        json_str = re.sub(r"[\r\n]", "", json_str)
        json_str_fixed = re.sub(r"(\w+):", r'"\1":', json_str)
        return json.loads(json_str_fixed)

    def group_variants(self, size_and_color_dict, color_properties):
        size_and_color_dict.sort(key=lambda x: x["property1"])
        variant_data = []
        for key, group in groupby(size_and_color_dict, key=lambda x: x["property1"]):
            group = list(group)
            sizes = [
                f'{item["property2"]}'
                if not item["property3"]
                else f'{item["property2"]}-{item["property3"]}'
                for item in group
                if item["availabilityCss"] in ["inStock", "text-primary"]
            ]

            variation_main_image = re.sub(r"\d{2}~460", f"{key}~1080", self.main_image)
            if len(sizes) == 0:
                sizes_str = "サイズ OneSize"
            else:
                sizes_str = self.size(sizes)
            variant_data.append(
                {
                    "color": color_properties[key],
                    "size": sizes_str,
                    "price": float(group[0]["price"].replace("$", "")),
                    "sale_price": float(group[0]["finalPromoPrice"].replace("$", "")),
                    "product_code2": self.product_code + key,
                    "image1": variation_main_image,
                }
            )
        return variant_data

    def get_gender(self, soup) -> str | None:
        parser = parsel.Selector(str(soup))
        for elem in parser.xpath('//ol[@class="breadcrumbs"]//li/a/text()').getall():
            if "Women" in elem:
                return "Women"
            elif "Men" in elem:
                return "Men"
        else:
            return None
