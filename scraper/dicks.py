import json
import logging
import math
import random
import re
import time
from collections import defaultdict
from collections.abc import Generator
from datetime import datetime

import curl_cffi
import parsel

from voracity2.lib.cf_provider import CFProvider

# from voracity2.lib.sb_provider2 import SBProvider2
from voracity2.lib.utils import ResultDict, ResultList, Status
from voracity2.lib.web_provider import FetchpageResponse
from voracity2.models.category import Category
from voracity2.models.item import Item
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DicksScraper(BaseScraper):
    site_id: int = 34
    site_name: str = "dicks"
    domain: str = "www.dickssportinggoods.com"
    allowed_genders = ["Men's", "Women's", "Unisex"]
    block_status = [403, 451, 500]
    block_messages = [
        "Something Went Wrong",
        "website is currently unavailable in your area.",
        "We apologize for any inconvenience.",
        # "<html>",
    ]
    # page_scroll_to_line: int = 1000

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
    }
    page_wait_for: str = '//button[contains(@class,"bottom-pagination-number")]'
    item_locator: str = '//div[contains(@class,"product-card-image")]/a'
    item_wait_for: str = '//img[@data-testid="MainLogo-desktop-logo"]'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=CFProvider(options=options))
        # super().__init__(web_provider=SBProvider2(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        product_number_str = parser.xpath(
            '//div[@class="top-pagination-product-number"]/text()'
        ).get()
        if not product_number_str:
            return 0

        if m := re.match(r"(\d+)", product_number_str.strip()):
            product_number = int(m.group(1))
        else:
            return 0

        max_page_no = math.ceil(product_number / 48)

        return max_page_no

    def get_sku(self, page_: Page_, item_url: str) -> str:
        """
        SKUを取得します。

        Args:
            page_ (Page_): ページオブジェクト。
            item_url (str): アイテムのURL。

        Returns:
            str: SKU。
        """
        # https://www.dickssportinggoods.com/p/zephyr-north-carolina-courage-team-red-adjustable-hat-21zepumlscrgrdddhmls/21zepumlscrgrdddhmls

        sku = item_url.split("/")[-1]

        return sku

    def get_listpage_url(self, category_url, page_no) -> Category:
        base_url = category_url.split("?")[0]
        if page_no == 1:
            return f"{base_url}?selectedSort=6"
        else:
            return f"{base_url}?selectedSort=6&pageNumber={page_no-1}"

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
                        # "https://www.toyota.com/",
                        # "https://www.google.com/",
                        # "https://www.dickssportinggoods.com/",
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
        #    def parse_item(self, html: str, page_: Page_, url: str) -> Generator[dict, None, dict]:
        """
        基本情報: //script[@id="dcsg-ngx-pdp-server-state"]
        """
        base_data = {
            "site_id": self.site_id,
            "page_id": page_.id,
            "status": Status.END_OK,
            "url": page_.url,
            "updated_at": datetime.now(),
            "updated_by": self.hostname,
        }

        try:
            parser = parsel.Selector(html)
            data: dict = json.loads(
                parser.xpath('//script[@id="dcsg-ngx-pdp-server-state"]/text()').get()
            )
            for key, val in data.items():
                if key.startswith("product-url-"):
                    data2 = val
                    break

        except Exception as e:
            logger.error(f"{page_.id}: No JSON data found {str(e)}")
            return "No JSON data found"

        ret = self.get_common_data(data2)
        if ret.code != Status.END_OK:
            return ret.message

        common_data = base_data | ret.data
        bread_crumbs = parser.xpath("//pdp-breadcrumb//li//a/span/text()").getall()
        common_data = self.insert_categories(common_data, bread_crumbs)

        ret = self.get_variant_data(data2)
        if ret.code != Status.END_OK:
            return "No variant data found"

        for record in self.create_records(common_data, ret.data):
            yield record | {"status": Status.END_OK, "result_text": "OK"}

    def create_records(self, common_data: dict, variant_data: list) -> list:
        if not variant_data:
            return [common_data] if common_data else []
        records = []
        for data in variant_data:
            data.update(common_data)
            records.append(data)
        return records

    def get_common_data(self, data: dict) -> ResultDict:
        products = data["productsData"]
        product = products[0]

        product_id = product["style"]["partNumber"]
        brand = gender = None
        for attr in product["style"]["descriptiveAttributes"]:
            match attr["name"]:
                case "Brand":
                    brand = attr["value"]
                case "Gender":
                    gender = attr["value"]

        if gender not in self.allowed_genders:
            return ResultDict(code=Status.END_ERROR, message=f"Not allowed gender: {gender}")

        common_data = {
            "name": product["style"]["name"],
            "sku": product_id,
            "currency": "USD",
            "brand": brand,
            "gender": gender,
        }

        return ResultDict(code=Status.END_OK, message="OK", data=common_data)

    def get_variant_data(self, data: dict) -> ResultList:
        try:
            products = data["productsData"]
            product = products[0]
            product_id = product["style"]["partNumber"]

            if "skus" in product:
                variations = [v.data for v in self.get_variant_data1(product_id, product["skus"])]
            else:
                return ResultList(code=Status.END_ERROR, message="no skus")

            if len(variations) == 0:
                return ResultList(code=Status.END_ERROR, message="No variation")
            else:
                return ResultList(code=Status.END_OK, message="OK", data=variations)
        except Exception as e:
            return ResultList(
                code=Status.END_ERROR, message=f"unknown file format: {product_id} {e}"
            )

    def normalize_price(self, price):
        if type(price) is float:
            return math.floor(price * 100) / 100

        return price

    def get_variant_data1(self, product_id: str, skus: dict) -> Generator[ResultDict, None, None]:
        sorted_skus = sorted(
            skus,
            key=lambda x: (
                x["prices"].get("listprice", 0),
                x["prices"].get("minlistprice", 0),
                x["prices"].get("offerprice", 0),
                x["partNumber"],
            ),
        )

        grouped_skus = defaultdict(list)
        for sku in sorted_skus:
            if "definingAttributes" not in sku:
                continue

            color = None
            for da in sku.get("definingAttributes"):
                if not da["isDisplayable"]:
                    continue

                if da["name"] == "Color":
                    color = da["value"]

            if sku.get("shipQty", 0) > 0:
                grouped_skus[color].append(sku)

        for color, skus2 in grouped_skus.items():
            image_json = self.request_image(product_id, color)
            image_urls = self.parse_image(image_json)

            sizes = []
            for sku in skus2:
                product_id = sku["parentPartNumber"]
                prices = sku["prices"]
                variation = {
                    "price": self.normalize_price(
                        prices.get("listPrice", prices.get("minlistprice"))
                    ),
                    "sale_price": self.normalize_price(prices.get("offerPrice")),
                    "product_code": sku["partNumber"],
                    "key": f"{product_id}#{sku['partNumber']}",
                    "color": color,
                }

                size = width = None
                for da in sku["definingAttributes"]:
                    match da["name"]:
                        case "Size":
                            size = da["value"]
                        case "Shoe Size":
                            size = da["value"]
                        case "Shoe Width":
                            width = da["value"]

                if size is None:
                    size_str = "OneSize"
                elif width is None:
                    size_str = size
                else:
                    size_str = f"{size}-{width}"
                sizes.append(size_str)

            sizes2 = [re.sub(" ", "-", size) for size in sizes]
            size_str2 = "サイズ " + " ".join(list(set(sizes2)))
            variation["size"] = size_str2
            # self.logger.info(f"variation: {variation}")
            variation = self.insert_images(variation, image_urls, 1)

            yield ResultDict(code=Status.END_OK, message="OK", data=variation)

    def request_image(self, product_id: str, color_name: str | None) -> dict | None:
        base_url = "https://dks.scene7.com/is/image/GolfGalaxy"

        if color_name is None:
            color_code = ""
        else:
            color_code = re.sub(r" ", "_", color_name)
            color_code = "_" + re.sub(r"/", "_", color_code)

        request_url = (
            base_url
            + f"/{product_id}{color_code}_is?req=set,json,UTF-8&labelkey=label&handler=customScene7Handler"
        )

        try:
            r = curl_cffi.get(request_url, impersonate="chrome133a", timeout=10)
        except Exception as e:
            logger.debug(e, stack_info=True)
            raise e

        try:
            if not r.text.startswith("/*"):
                raise Exception(f"Invalid image api response #1 {product_id} {r.text}")
            response_json = re.findall(r"{.*}", r.text)
            if response_json:
                return json.loads(response_json[0])
            else:
                raise Exception(f"Invalid image api response #2 {product_id} {response_json}")
        except Exception as e:
            raise Exception(f"Invalid image api response #3 {product_id} {e}")

    def parse_image(self, image_json: dict | None):
        try:
            image_urls = []
            if image_json is None:
                return image_urls

            image_base_url = "https://dks.scene7.com/is/image/"
            if image_json.get("set") is None:
                return image_urls

            items = image_json["set"]["item"]
            if type(items) is not list:
                items = [items]
            for item in items:
                if item.get("i") is None:
                    continue
                image_urls.append(image_base_url + item["i"]["n"])
            return image_urls
        except Exception as e:
            logger.error(f"parse image error: {image_json}")
            raise e

    def json_dumpf(self, filepath: str, data: dict | list):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False))
