import json
import logging
import re
from datetime import datetime
from socket import gethostname
from typing import Generator

import bs4

from voracity2.lib.bin_search import bin_search_dict
from voracity2.lib.utils import ResultDict, ResultList, Status
from voracity2.models.page_ import Page_
from voracity2.scraper.base_item import BaseItemScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class YooxItemScraper(BaseItemScraper):
    site_id: int = 31
    domain = "yoox.com"
    list_locator = '//li[@class="item"]//a'
    block_status = [403]
    block_messages = ["Access Denied"]
    randomize_location = True

    def get_itemurl(self, url):
        url = super().get_itemurl(url)
        url = url.split("#")[0]
        return url

    def parse_item(self, html: str, page_: Page_, url: str) -> Generator[dict, None, None]:
        try:
            soup = self.create_soup(html)
            ret = self.get_common_data(soup)
            if ret.code != Status.END_OK:
                return

            common_data = ret.data.copy()
            common_data.update(
                {
                    "site_id": self.site_id,
                    "page_id": page_.id,
                    "status": Status.END_OK,
                    "url": url,
                    "updated_at": datetime.now(),
                    "updated_by": self.hostname,
                }
            )
            ret = self.get_variant_data(soup)
            if ret.code != Status.END_OK:
                return

            variant_data = ret.data.copy()
            records = self.create_records(common_data, variant_data)

            for record in records:
                record.update(
                    {
                        "key": f"{common_data['product_code']}#{record['color']}",
                        "status": Status.END_OK,
                        "updated_at": datetime.now(),
                        "updated_by": gethostname(),
                    }
                )
                yield record

        except Exception as e:
            logger.error(f"parse_product: {e}")

    def create_soup(self, html: str) -> bs4.BeautifulSoup:
        soup = bs4.BeautifulSoup(html, "lxml")
        return soup

    def get_common_data(self, soup) -> ResultDict:
        json_item = soup.select_one("script#__NEXT_DATA__").text
        product = json.loads(json_item)
        name_json = soup.select_one('script[type="application/ld+json"]')
        name_json_str = json.loads(name_json.text)
        name = name_json_str["name"]
        base_image_url = name_json_str["image"][0]
        self.base_image_path = re.findall(
            r"^https://www.yoox.com/images/items/\d+?/", base_image_url
        )[0]

        product_code = product["props"]["pageProps"]["initialState"]["itemApi"]["code"]
        product_code = re.sub(r"\w.$", "", product_code)
        brand = product["props"]["pageProps"]["initialState"]["itemApi"]["brand"]["name"]

        common_data = {
            "name": name,
            "sku": product["props"]["pageProps"]["initialState"]["itemApi"]["code"],
            "product_code": product_code,
            "brand": brand,
            "gender": product["props"]["pageProps"]["initialState"]["itemApi"]["area"],
            "site_id": self.site_id,
            "currency": "USD",
        }
        # カテゴリはgender, pntln1, pntln, brand
        if self.site_id == 31:
            category = "WOMEN"
        else:
            category = "MEN"
        microCategory = product["props"]["pageProps"]["initialState"]["itemApi"].get(
            "microCategory"
        )
        if microCategory is None:
            return ResultDict(code=Status.END_ERROR, message="no micro category")

        categories = [
            "HOME",
            category,
            product["props"]["pageProps"]["initialState"]["itemApi"]["macroCategory"][
                "singleDescription"
            ],
            microCategory["singleDescription"],
            brand,
        ]
        common_data = self.insert_categories(common_data, categories)
        return ResultDict(code=Status.END_OK, message="OK", data=common_data)

    def get_variant_data(self, soup) -> ResultList:
        json_item = soup.select_one("script#__NEXT_DATA__").text
        product = json.loads(json_item)
        item_api = product["props"]["pageProps"]["initialState"]["itemApi"]
        sizes = item_api["sizes"]
        sale_price = item_api["priceFinal"]["transactional"]["amount"]
        price = item_api.get("priceOriginal")
        if price is not None:
            price = price["transactional"]["amount"]
        else:
            price = sale_price
        size_map = []
        for size in sizes:
            size_map.append({"size_id": size["id"], "size_name": size["default"]["text"]})
        colors = item_api["colors"]

        variant_data = []
        for color in colors:
            size_list = []
            color_name = color["name"]
            product_code2 = color["code10"]
            image_formats = color["imageFormats"]
            image_format_list = [
                image_format for image_format in image_formats if "14" in image_format
            ]
            image_urls = [
                self.base_image_path
                + product_code2
                + "_"
                + key
                + ".jpg?impolicy=crop&width=1571&height=2000"
                for key in image_format_list
            ]
            for instock in color["availableSizesIds"]:
                size_dict = bin_search_dict(size_map, instock["id"], "size_id")
                if not size_dict:
                    return ResultList(code=Status.END_ERROR, message="Product size couldn't find")

                size_list.append(re.sub(r" ", "", size_dict["size_name"]))
                if size_list == ["--"]:
                    size_str = "サイズ One-Size"
                else:
                    size_str = "サイズ " + " ".join(size_list)
            variation_record = {
                "color": color_name,
                "size": size_str,
                "product_code2": product_code2,
                "price": price,
                "sale_price": sale_price,
            }
            variation_record = self.insert_images(variation_record, image_urls, start_index=1)
            variant_data.append(variation_record)
        return ResultList(code=Status.END_OK, message="OK", data=variant_data)
