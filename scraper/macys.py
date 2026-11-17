import json
import logging
import re
import urllib
from collections.abc import Generator
from datetime import datetime

import parsel

from voracity2.lib.bin_search import bin_search_dict
from voracity2.lib.cc_provider import CCProvider
from voracity2.lib.utils import Status
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MacysScraper(BaseScraper):
    site_id: int = 36
    site_name: str = "macys"
    domain = "www.macys.com"
    cookies = {
        "shippingCountry": "US",
        "currency": "USD",
    }
    # headers = {
    #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
    # }
    item_locator = '//div[@class="product-image"]//a'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=CCProvider(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        max_page_no = int(
            parser.xpath('(//a[contains(@class,"page-number-item")])[last()]/text()').get()
        )

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> str:
        # https://www.macys.com/shop/womens-clothing/all-plus-size-clothing/Pageindex,Sortby/1,NEW_ITEMS?id=188853
        # https://www.macys.com/shop/mens-clothing/mens-accessories/Pageindex/1?id=47665
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

    def get_json(self, html: str, key_string: str):
        parser = parsel.Selector(html)
        data = parser.xpath(f'//script[contains(text(), "{key_string}")]/text()').get()

        if m := re.match(r".*=({.*});", data, re.DOTALL):
            data2 = m.group(1)
            data2 = data2.replace("undefined", "null")
            if dict_data := json.loads(data2):
                return dict_data
            else:
                None
        else:
            return None

    def parse_item(self, page_: Page_, html: str) -> Generator[dict, None, str]:
        json_data = self.get_json(html, "window.__INITIAL_STATE")
        if json_data is None:
            return "No JSON data found"

        item_info = json_data["pageData"]["product"]["product"]
        logger.info(item_info["detail"]["name"])

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
        _common_data = self.get_common_data(item_info)
        if _common_data is None:
            return "No common data found"

        variant_data = self.get_variant_data(item_info)
        for record in self.create_records(_common_data, variant_data):
            yield base_data | record

    def get_common_data(self, product):
        detail = product["detail"]
        common_data = {
            "name": detail["name"],
            "brand": detail["brand"]["name"],
            "product_code": product["id"],
            "url": self.get_abs_url(product["identifier"]["productUrl"]),
        }
        categories = [
            category["name"] for category in product["relationships"]["taxonomy"]["categories"]
        ]

        try:
            if detail["name"].startswith("Men") or categories[0].startswith("Men"):
                common_data["gender"] = "Men"
            elif detail["name"].startswith("Women") or categories[0].startswith("Women"):
                common_data["gender"] = "Women"
        except Exception:
            pass

        common_data = self.insert_categories(common_data, categories)
        return common_data

    def get_variant_data(self, product):
        variant_data = []
        append = variant_data.append
        traits = product["traits"]
        colors = traits["colors"]["colorMap"]
        for color_id, color in colors.items():
            prices = [
                price["values"][0]["value"]
                for price in color["pricing"]["price"]["tieredPrice"]
                if price["values"][0]["type"] in ["regular", "discount"]
            ]
            # logger.info(
            #     [price["values"][0]["type"] for price in color["pricing"]["price"]["tieredPrice"]]
            # )
            if len(prices) == 1:
                price = prices[0]
                sale_price = None
            else:
                try:
                    price, sale_price = prices
                except Exception as e:
                    logger.warning(f"Error: {e}")
                    logger.debug(json.dumps(color["pricing"]["price"]["tieredPrice"], indent=2))
            variation = {
                "color": color["name"],
                "size": self.get_size_str(traits, color),
                "price": price,
                "sale_price": sale_price,
                "sku": color_id,
                "key": f"{color_id}#{color['name']}",
            }
            variation = self.insert_images(variation, self.get_images(color), 1)
            append(variation)
        return variant_data

    def get_size_str(self, traits, color) -> str:
        if traits.get("sizes") is None:
            return "サイズ One-Size"
        size_map = traits["sizes"]["sizeMap"].values()
        sizes = [
            re.sub(
                r" ",
                "-",
                bin_search_dict(list(size_map), i, "id")["displayName"],
            )
            for i in color["sizes"]
        ]
        return "サイズ " + " ".join(sizes)

    def get_images(self, color) -> list[str]:
        return [
            urllib.parse.urljoin(
                "https://slimages.macysassets.com/is/image/MCY/products/",
                image["filePath"] + "?wid=1230&hei=1500",
            )
            for image in color["imagery"]["images"]
        ]
