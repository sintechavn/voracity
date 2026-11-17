import json
import logging
import math
import re
from collections.abc import Generator
from datetime import datetime
from urllib.parse import urlencode

import parsel

from voracity2.lib.cc_provider import CCProvider
from voracity2.lib.utils import Status
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class AsosScraper(BaseScraper):
    site_id: int = 40
    site_name: str = "asos"
    domain = "www.asos.com"
    cookies = {
        "geocountry": "US",
        "browseCurrency": "USD",
        "currency": "2",
        "browseCountry": "US",
        "browseSizeSchema": "US",
        "storeCode": "US",
        "asos": "currencyid=2&currencylabel=USD&topcatid=1000",
        "browseLanguage": "en-US",
    }
    not_found_status: list[int] = [404, 410]

    item_locator = '//li[@aria-label="product"]/a'

    def __init__(self, options: dict = {}):
        super().__init__(web_provider=CCProvider(options=options))

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        max_page_no = math.ceil(int(parser.xpath("//progress/@max").get()) / 72)

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> str:
        # https://www.macys.com/shop/womens-clothing/all-plus-size-clothing/Pageindex,Sortby/1,NEW_ITEMS?id=188853
        # https://www.macys.com/shop/mens-clothing/mens-accessories/Pageindex/1?id=47665
        params = {
            "offset": (page_no - 1) * 72,
            "includeNonPurchasableTypes": "restocking",
            "store": "US",
            "lang": "en-US",
            "currency": "USD",
            "rowlength": "4",
            "channel": "desktop-web",
            "country": "US",
            "customerLoyaltyTier": "null",
            # "keyStoreDataversion": "4i7nlxk-44",
            # "advertisementsPartnerId": "100716",
            # "advertisementsVisitorId": "e7a7d5d0-0db2-4f82-885a-2bc11f2778ec",
            # "advertisementsOptInConsent": "true",
            "limit": "72",
        }
        param_str = urlencode(params)

        if m := re.search(r"cid=(\d+)", category_url):
            url = f"https://www.asos.com/api/product/search/v2/categories/{m.group(1)}?{param_str}"

            return url
        else:
            return ""

    def parse_listpage(self, page_: Page_, html: str):
        """
        リストページを解析します。

        Args:
            page_ (Page_): リストページオブジェクト。
            driver (Any): ドライバオブジェクト。
        """
        data = json.loads(html)

        for idx, product in enumerate(data["products"], start=1):
            item_url = f'https://{self.domain}/us/{product["url"]}'
            sku = f"{product["id"]}#{product["colour"]}"
            logger.info(f"{idx}: {item_url}")

            if self.item_exists(sku):
                logger.info(f"page:{page_.id}: SKIP item {item_url} exists")
                continue

            yield {
                "site_id": self.site_id,
                "category_id": page_.category_id,
                "category_url": page_.category_url,
                "status": Status.PENDING,
                "url": item_url,
                "sku": sku,
                "updated_at": datetime.now(),
                "updated_by": self.hostname,
            }

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
        json_data = self.get_json(soup, "window.__INITIAL_STATE")
        if json_data is None:
            return "No JSON data found"

        try:
            _common_data = self.get_common_data(soup)
            if _common_data is None:
                return "No data"
        except Exception as e:
            return str(e)

        yield base_data | _common_data

    def get_common_data(self, soup):
        product_sub_data = self.get_json(soup, "")
        price_info_list = self.get_price_and_stocks(soup)
        price_info = next(
            item for item in price_info_list if item["productId"] == product_sub_data["id"]
        )
        sku = self.get_sku_(product_sub_data)
        price_list = price_info["productPrice"]
        sale_price = price_list["current"]["value"]
        price = price_list["previous"]["value"]
        in_stock_variation_ids = [
            variation["id"] for variation in price_info["variants"] if variation["isInStock"]
        ]
        variants = product_sub_data["variants"]
        color = variants[0]["colour"]
        in_stock_variation_sizes = [
            variant["size"]
            for variant in variants
            if variant["variantId"] in in_stock_variation_ids
        ]
        size_str = self.size(in_stock_variation_sizes)
        parsed_size_str = re.sub(r"-+", "-", size_str)
        common_data = {
            "name": product_sub_data["name"],
            "site_id": self.site_id,
            "currency": "USD",
            "product_code": sku,
            "product_code2": product_sub_data["productCode"],
            "sku": sku,
            "color": color,
            "brand": product_sub_data["brandName"],
            "gender": product_sub_data["gender"],
            "size": parsed_size_str,
            "price": price,
            "sale_price": sale_price,
            "key": f"{sku}#{color}",
        }
        images = self.get_images(soup)
        common_data = self.insert_images(common_data, images, 1)
        categories = [product_sub_data["productType"]["name"]]
        common_data = self.insert_categories(common_data, categories)

        return common_data

    def get_json(self, soup, key_string):
        scripts = soup.select("script")
        script = [
            str(script) for script in scripts if "window.asos.pdp.config.product =" in str(script)
        ][0]
        variations_json = re.findall(r"window\.asos\.pdp\.config\.product = (.*?);", script)[0]
        variations = json.loads(variations_json)

        return variations

    def get_price_and_stocks(self, soup):
        scripts = soup.select('script[type="text/javascript"]')
        script = [
            str(script)
            for script in scripts
            if "window.asos.pdp.config.stockPriceResponse" in str(script)
        ][0]
        variations_json = re.findall(
            r"window\.asos\.pdp\.config\.stockPriceResponse = (.*?);", script
        )[0]
        valid_variation_json = re.sub(r"\'", "", variations_json)

        return json.loads(valid_variation_json)

    def get_images(self, soup):
        images = [
            re.sub(r"\$n_240w\$", "", re.sub(r"wid=40", "wid=600", image.get("src")))
            for image in soup.select(".image-thumbnail img")
        ]
        return images

    def get_sku_(self, product_sub_data):
        sku = str(product_sub_data["id"])
        if len(sku) == 8:
            sku = "0" + sku
        elif len(sku) == 7:
            sku = "00" + sku
        sku = "01-" + sku
        return sku
