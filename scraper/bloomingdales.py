import json
import logging
import re
import urllib
from collections.abc import Generator
from datetime import datetime
from itertools import groupby

import parsel

from voracity2.lib.bin_search import bin_search, bin_search_dict
from voracity2.lib.cc_provider import CCProvider
from voracity2.lib.utils import Status
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BloomingdalesScraper(BaseScraper):
    site_id: int = 39
    site_name: str = "bloomingdales"
    domain = "www.bloomingdales.com"
    cookies = {
        "shippingCountry": "US",
        "currency": "USD",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36",
        "accept-language": "en-US",
    }
    item_locator = '//a[@class="brand-and-name"]'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=CCProvider(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        max_page_no = parser.xpath('//select[@aria-label="Page"]/option[last()]/@value').get()
        if max_page_no is None:
            max_page_no = parser.xpath(
                '(//a[contains(@class, "page-number-item")])[last()]/text()'
            ).get()

        if max_page_no is None:
            logger.info("No max page number found")
            return 1
        else:
            max_page_no = int(max_page_no)
            return max_page_no

    def get_listpage_url(self, category_url, page_no) -> str:
        # https://www.bloomingdales.com/shop/womens-apparel/designer-cocktail-dresses/Pageindex/3?id=1005206
        url = re.sub(r"/(\d+)", f"/{page_no}", category_url)

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
        # https://www.macys.com/shop/product/plus-size-printed-maxi-dress?ID=188853
        # https://www.macys.com/shop/product/plus-size-printed-maxi-dress?ID=188853&CategoryID=188853&swatchColor=Black%2FWhite
        # https://www.macys.com/shop/product/plus-size-printed-maxi-dress?ID=188853&swatchColor=Black%2FWhite
        # https://www.macys.com/shop/product/plus-size-printed-maxi-dress?ID=188853&swatchColor=Black%2FWhite&swatchSize=1X

        if m := re.match(r".+\?ID=(\d+)", item_url):
            sku = m.group(1)
        else:
            sku = item_url

        return sku

    def parse_item(self, page_: Page_, html: str) -> Generator[dict, None, str]:
        soup = parsel.Selector(html)
        json_data = self.get_json(soup, "window.__INITIAL_STATE__")
        if json_data is None:
            return "No JSON data found"

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
        _common_data = self.get_common_data(soup)
        if _common_data is None:
            return "No common data found"

        variant_data = self.get_variant_data(soup)
        for record in self.create_records(_common_data, variant_data):
            yield base_data | record

    def get_common_data(self, soup: parsel.Selector):
        mkt_data_json = soup.css("#productMktData::text").get()
        mkt_data = json.loads(mkt_data_json)
        common_data = {
            "name": mkt_data["name"],
            "site_id": self.site_id,
            "brand": mkt_data["brand"]["name"],
            "currency": "USD",
            "product_code": mkt_data["productID"],
        }
        categories = [
            category.strip() for category in soup.css("span.p-menuitem-text::text").getall()
        ]
        common_data = self.insert_categories(common_data, categories)
        return common_data

    def get_json(self, soup: parsel.Selector, key_string: str):
        for script in soup.css("script::text").getall():
            if key_string in str(script):
                product_json = re.findall(r"{.*};", str(script))[0].replace(";", "")
                js_object_literal_fixed = re.sub(r"\bundefined\b", "null", product_json)
                return json.loads(js_object_literal_fixed)

    def get_variant_data(self, soup: parsel.Selector):
        product_data = self.get_json(soup, "window.__INITIAL_STATE__")
        product = product_data["pageData"]["product"]
        product_relationship = product["product"]["relationships"]
        product_id = product_data["pageData"]["productId"]
        if "memberProductMap" in product_relationship:
            self.debug_logger.warning("収集対象外")
            return None
        selected_product_traits = product["product"]["traits"]
        if "sizes" not in selected_product_traits:
            size_map = None
            size_str = None
            exist_size_and_sku = []
        else:
            available_universal_product_codes = [
                int(universal_product_code)
                for universal_product_code, stock_value in product_relationship["upcs"].items()
                if stock_value["availability"]["available"]
            ]
            size_map = selected_product_traits["sizes"]["sizeMap"]
            exist_size_and_sku = self.get_exist_sizes_and_sku(
                available_universal_product_codes,
                product["product"]["traits"]["traitsMaps"]["upcMap"],
                size_map,
            )
        variations = []
        append = variations.append
        price_to_colors = selected_product_traits["traitsMaps"]["priceToColors"]
        for color_variation in product["product"]["traits"]["colors"]["colorMap"].values():
            images = color_variation["imagery"]["images"]
            image_urls = [
                urllib.parse.urljoin(
                    "https://images.bloomingdalesassets.com/is/image/BLM/products/",
                    image["filePath"],
                )
                + "?op_sharpen=1&wid=700&fit=fit"
                for image in images
            ]
            color_id = color_variation["id"]
            regular_price = color_variation["pricing"]["price"]["tieredPrice"][0]["values"][0][
                "value"
            ]
            price, sale_price = self.get_prices(color_id, price_to_colors, regular_price)
            size_and_sku = bin_search_dict(exist_size_and_sku, str(color_id), "sku")
            if size_and_sku:
                size_str = size_and_sku["size"]
                price, sale_price = self.get_prices(color_id, price_to_colors, regular_price)
            else:
                size_str = "サイズ One-Size"
            record = {
                "key": f"{product_id}#{color_id}",
                "color": color_variation["name"],
                "size": size_str,
                "price": price,
                "sale_price": sale_price,
                "sku": color_id,
                "product_code": product["product"]["id"],
            }

            gender = self.__gender(product_data)
            if gender:
                record["gender"] = gender

            record = self.insert_images(record, image_urls, 1)
            append(record)
        return variations

    def get_exist_sizes_and_sku(self, upcs, upc_map, size_map):
        skus_and_sizes = []
        skus_and_sizes_append = skus_and_sizes.append
        for product_code_and_index, upc in upc_map.items():
            if bin_search(upcs, upc):
                sku, size_index = product_code_and_index.split("_")
                size_map_values = list(size_map.values())
                size = bin_search_dict(size_map_values, int(size_index), "id")
                skus_and_sizes_append([sku, size["displayName"]])
        skus_and_sizes.sort()
        exist_size_and_sku = []
        exist_size_and_sku_append = exist_size_and_sku.append
        for _, group in groupby(skus_and_sizes, key=lambda m: m[0]):
            i = 0
            sku_sizes = list(group)
            sizes = [re.sub(r" ", "-", ele[1]) for ele in sku_sizes]
            size_str = "サイズ " + " ".join(sizes)
            exist_size_and_sku_append(
                {
                    "sku": sku_sizes[i][0],
                    "size": size_str,
                }
            )
            i += 1
        return exist_size_and_sku

    def get_prices(self, product_code2, price_to_colors, regular_price):
        for price_to_color in price_to_colors:
            if product_code2 in price_to_color["colorIds"]:
                price = float(price_to_color["price"].replace("$", "").replace(",", ""))
                if price_to_color["onSale"]:
                    sale_price = price
                    price = regular_price
                else:
                    sale_price = None

        return price, sale_price

    def __gender(self, product_data: dict):
        gender = product_data["pageData"]["product"]["meta"]["analytics"]["data"]["t_category_name"]
        if gender[0] == "Women" or gender[0] == "Men":
            return gender[0]
        else:
            return None
