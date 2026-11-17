import json
import re
from collections.abc import Generator
from datetime import datetime

import parsel

from voracity2.lib.cc_provider import CCProvider
from voracity2.lib.sb_provider import SBProvider
from voracity2.lib.utils import Status
from voracity2.lib.web_provider import FetchpageResponse
from voracity2.models.category import Category
from voracity2.models.item import Item
from voracity2.models.page_ import Page_
from voracity2.scraper.base import BaseScraper
from voracity2.settings import logger


class DswScraper(BaseScraper):
    site_id: int = 38
    site_name: str = "dsw"
    domain = "www.dsw.com"
    block_messages = ["Access Denied"]
    not_found_messages = [
        "NO RESULTS",
        "The page you're trying to reach cannot be found",
        "Sorry, we're tangled up",
    ]
    browser_args = {"block_images": False}
    popup_locator = ".button__close"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "baggage": "sentry-environment=prod,sentry-release=20241210.9,sentry-public_key=f148ab1680a9f00e56b5b091024b3edd,sentry-trace_id=111fd0df35624310b7592784e73ddb59,sentry-sample_rate=0.01,sentry-transaction=%2Fproduct%2F%3AprodName%2F%3AskuId%2F,sentry-sampled=false",
        # "cookie": "MOUS=0; BVBRANDID=477b6894-f0fa-4ed0-acb2-c8ac98b8a2b4; __rutma=262300170-fb-pi-43-1p-s0d3t6yx4449tsrkoq7n-1708266094486.1711170115178.1711179562516.4.5.1; smtrrmkr=638467763648101085%5E018dbc98-072e-4214-a020-971dba7f0db2%5E018e6a40-070a-4c85-b53b-31524ac01367%5E0%5E153.187.103.180; IR_PI=edda6f2f-ce68-11ee-926c-9dc2a1cfa8a5%7C1711179564532; __idcontext=eyJjb29raWVJRCI6IjJIT1RuQ1RiZklsVDZTY2RXYUVvVGlBRkJKaiIsImRldmljZUlEIjoiMkhPVG5CMnpjRGpSaHg5ZHIwN1REREZsYzVtIiwiaXYiOiIiLCJ2IjoiIn0%3D; ROUTEID=.ps011; _group=Group B; AMCVS_A8683BC75245AF560A490D4D%40AdobeOrg=1; fw_se={%22value%22:%22fws2.286fccce-0607-43ef-bdbf-0d1f11da4ba6.1.1729312869805%22%2C%22createTime%22:%222024-10-19T04:41:09.805Z%22}; fw_utm={%22value%22:%22{}%22%2C%22createTime%22:%222024-10-19T04:41:24.782Z%22}; fw_uid={%22value%22:%22eacc6dc0-e31a-4aa4-a1b9-2bb360d23571%22%2C%22createTime%22:%222024-10-19T04:41:24.783Z%22}; fw_bid={%22value%22:%22gpPaQg%22%2C%22createTime%22:%222024-10-19T04:41:25.305Z%22}; fw_chid={%22value%22:%22801VAM7%22%2C%22createTime%22:%222024-10-19T04:41:25.424Z%22}; ak_bmsc=E6F02AF3D95D70DB1926A00D0161C0F8~000000000000000000000000000000~YAAQrX/NFzirDM6TAQAAgMYaAxoZjnlUdmm+BUnSo+zoQvqGyOnBeE2I8/p800xsigmXCML29ulKbcirid020DAoAlqZcxUUGsn6/z7ooYCq03TuPPJ1oeBaBhk0Et2E/M7F8yJ5uAUbOteqlWawT56ij8EJOMyoQvWbjJ7OWhNb+DGCdQQGPfKVWgcTzqkt7mLooEW4tmsjyi2TNDVOK5k2185jQbxla5TYNJNKe1RI1YNxOsCHD/dzdhQNLZDJ0eC0Uswmlvwo0SlUjWXzl2LNyrUbaHi9wxSw5p3CSccUDXcPpzqoM+UV+lxGhyx6UZC9x7CurHJYtmp6Mj/Ou5Aq2W4gIiZu6L4eTibQKup3hgcWM8mZ13rqNUru07qD8wvzW5RXcA==; _abck=C8D91595CCE2F91E9F6277048BCF5A6C~0~YAAQrX/NF3GrDM6TAQAAWskaAw3QE6p5EXQJl1xhLI1d9FNDmitNq3eTMWCHmao62VpZZ62HRzKFTw1Zf7xa9IBnFVHaQrRLOoQcLbybipSpNOxKCpdCB1pONx19m3tltNYW8mXyPjxsXgVvD7Bju4cz0oi47B1aXy6I5hiKDDMTMUtW9NGAx8IaVdvVsCnjfUJr/5kJImGGlqhrnphMRg6nN4s4+Ax+e6iaiNu3fcA6k6qyoya70XLREZ9CuGxTiLQEkqdAxUWq3XAhyaPTDIWCgdTjevxA9LUhkV0jyc4qAunLA25GQNSa6ccI3mWxFg1K4VJvBWWz0FtTNOFTo0F/ZDPZhWJj10FrqDX6CG3giiBTzOKYRRMGMA4USp2dLkfORICYB1dARG9tLPgNTGQxOFkSc2RN2tHCzW0mDaWwBp3HT9XiJdRitnSkc83eae+nyabZsRMcVokYUM9hysMkTWOPUqAAkw6mlgSVeQ2r6tvY9J62Vg==~-1~-1~-1; JSESSIONID=uyoDGs1wWWjsBOrEyVasxJ0dDa1yC0FCk9RUOkAyXwtQnIaaj6fG!-376233376; _sp_ses.77b1=*; prev_page_name=pdp:578785:kaia wedge bootie; prev_page_type=product details; utag_adobe=; prev_page_name_2=pdp:578785:kaia wedge bootie; prev_page_name_3=category:women:shoes:womens shoes; AMCV_A8683BC75245AF560A490D4D%40AdobeOrg=1176715910%7CMCIDTS%7C20084%7CMCMID%7C39106845879972998488278803460349790353%7CMCAID%7CNONE%7CMCOPTOUT-1735226099s%7CNONE%7CvVersion%7C5.4.0; utag_main=v_id:0192a314250b003ce923ba965dcc05075004106d009dc$_sn:3$_ss:0$_st:1735220699554$vapi_domain:dsw.com$dc_visit:3$ses_id:1735218875396%3Bexp-session$_pn:2%3Bexp-session$dc_event:3%3Bexp-session; _sp_id.77b1=a1237261-19c7-4a59-8294-07375b08e626.1734924791.2.1735218900.1734924793.149391ab-d2f6-4851-ac62-32f5f07d3621; bm_mi=1D94729B3536ACC80DD2E40BE54ADD85~YAAQrX/NF7DRDM6TAQAA4JccAxr9r/SAffrTLS45XhFjdadnJp3cnL8O/ket6Q7N3Uk8XcEJGJNmouHm0R21gcAxheeOJBd0DM8GSdQuk1uLk4NcCujkq/X8ClXs9CxBf/8m+p1Guaude1ktAbRiF9y3VCIN9Kg7xAHQ5MUIXNG3umze/Sqnxmlme8ZCVH9Ko+f3TA+o7nJ5tlgWvAkFaisqk69KSukZaTkRLWD3hSl9pkIpCxCrmNH4fYvl9VF1b3PJ/GzHIPmAGMZWCmhqevPeYGIZ9udy+gV5C5naRwYDoo9zN5sBEFrP6VYW7+Jnfr+/PelZ4yaqxTV9RcdcZ0oKWrUROvnQGu8Wkdcw+L8=~1; bm_sz=BE7FD9C046F2227450FFBDED24325AFF~YAAQrX/NF7LRDM6TAQAA4JccAxoCzW2L57PWoRHxkrXMSpumFHjI/+ADu2QG72l4lfBV8OLDfId/0CSjb/swSc0d5HLwpUzz3xeyxabx2Ehy0DLKlrPbsJ9dyAVCvCcy/e2Pb+xAzN9diGPhm0hk42HbB8Z4DBxJUG5IWe3dbmJnupjmjpM/DtbEAmRPDbZJegJRKqMgP05nFl0Z0qykgHcWxDa3ncSTzzQurwmCGXMQKhmvB5doaOi6lxCN8aNBB/tubX0zfTmjnzzRT5LEiKSCaeqERbRTuDEWzl1teYO1zdkz7Vm9oi1E48nQuUSZ4riSvymUyPZfyqBVs2nTyQP3bRQZkzALqTOzDd+eCHBFiPuDFT/sCdF3qLPMiV7FNAN21iZMBi86vrEjETpHXnwogZvOxVHAAA==~3228469~4600633; ATGSESSION=eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiJ9.eyJhdWQiOiJ3d3cuZHN3LmNvbSIsInN1YiI6IjIxMTYwOTIyNTU2IiwidXNlclN0YXR1cyI6IkFOT05ZTU9VUyIsImlzcyI6IkFURyIsImV4cCI6MTczNTIyMDc5MywiaWF0IjoxNzM1MjE4OTkzfQ.6Iu1E3pN3sqDRoXfnVoSnOXJpjCXyhBFof5hj0b62nJIp7WOBGQPwaTS8sW0sDSU21VI3fRgmqJB8rujyyCrAg; bm_sv=0D03CC464820148F3467CAED50DDDA99~YAAQrX/NF/3RDM6TAQAAM5wcAxqxPwrV/Vue0oF+fuxfSeiMTV24qcSH82Wtl6qF2rIdmW9ya7b+en7TxqIVCbptTJ6u3+z+HPsj/Y3w9kNY+fGbgkYsOZrZogC8U8QP0JMnzGKY/cuI2zlrvOxT5OlqNLBA/jwDRjdbTxmTYq9NGU9RZ6exktGKvHtPRFv2lFbg4SytCoBIl6f1Y6U+jHy6WwHgEOYexF1V6CIoDh5rJ9ZNLNYEFLq+l7xL~1",
        "dnt": "1",
        "if-none-match": 'W/"69eb-gfO72eydu8q9cQ/ek9mQhDs/g+s"',
        "origin": "https://www.dsw.com",
        "priority": "u=1, i",
        "referer": "https://www.dsw.com/product/toms-kaia-wedge-bootie/578785?activeColor=101",
        "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "sentry-trace": "111fd0df35624310b7592784e73ddb59-a38293ebc6ca0eca-0",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-dbi-app-id": "ecomm-web",
        "x-dbi-app-version": "2.0.0",
        "x-dbi-build-number": "20241210.9",
        "x-dbi-sig-digest": "ZjFkNDM1ODlhYjM0N2ZmZjQwNzA3NzFlN2IyNTc2MDU5Y2ViZjEzN2NjZmI5NDU5YTI4ZGM3MmVkYWI5YWFhNw==",
        "x-dbi-sig-salt": "oLnhipTj",
        "x-dbi-sig-version": "1",
        "x-request-timestamp": "1735218992",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/",
    }

    page_wait_for = "li.pagination-page"
    page_scroll_to_line = 2000
    max_page_locator = '//li[contains(@class,"pagination-page")]//a'

    page2_wait_for: str = "a.product-tile__pdp-link"
    page2_scroll_to_line = 2000
    item_locator = '//a[@class="product-tile__pdp-link"]'

    def __init__(self, options: dict = {}):
        super().__init__(
            web_provider=SBProvider(options=options | self.browser_args),
            options=options,
        )

    def get_max_page_no(self, html: str) -> int:
        parser = parsel.Selector(html)
        max_page = parser.xpath('//li[contains(@class,"pagination-page")][last()]//a/text()').get()
        if not max_page:
            max_page_no: int = 1
        else:
            max_page_no: int = int(max_page.strip())

        return max_page_no

    def get_listpage_url(self, category_url, page_no) -> Category:
        base_url = category_url.split("?")[0]

        if page_no == 1:
            return f"{base_url}"
        else:
            return f"{base_url}?No={page_no}"

    def get_sku(self, page_: Page_, item_url: str) -> str:
        if m := re.match(r".+\/(\d+)\?", item_url):
            return m.group(1)
        else:
            return ""

    def crawl_item(self):
        """
        クロール処理を実行します。
        """
        self.web = CCProvider(options=self.options | self.browser_args)

        for _page_ in self._get_next(self.site_id, Page_):
            page_: Page_ = _page_

            try:
                product_id = re.findall(r"/(\d+)", page_.url)[0]
            except IndexError:
                return ""

            try:
                logger.info(page_.url)
                response: FetchpageResponse = self.web.fetch_page(
                    f"https://api.dsw.com/item/api/v1/item/{product_id}?channel=dsw_us_digital&locale=en_us&include_summary_kind=review_summary_short",
                    headers=self.headers
                    | {
                        "Referer": page_.url,
                    },
                    block_status=self.block_status,
                    not_found_messages=self.not_found_messages,
                    block_messages=self.block_messages,
                )
                if response.status_code == 404:
                    self.update_status(page_, Status.END_ERROR, "Page not found")
                    continue
                items: list[dict] = [i for i in self.parse_item(page_, response.text)]
                self.save_data(items, Item)
                self.update_status(page_, Status.END_OK, "OK")
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
            "currency": "USD",
            "url": page_.url,
            "updated_at": datetime.now(),
            "updated_by": self.hostname,
        }

        data = json.loads(html)

        common_data = self.get_common_data(data)
        if type(common_data) is str:
            return common_data

        variant_data = self.get_variant_data(data)

        for record in self.create_records(common_data, variant_data):
            yield base_data | record

    def get_common_data(self, soup) -> dict | str:
        common_data = {}
        price = self.get_price(soup)
        if price == 0:
            return "No price found"
        common_data["name"] = self.get_name(soup)
        common_data["brand"] = self.get_brand(soup)
        common_data["sku"] = self.get_sku_(soup)
        common_data["site_id"] = self.site_id
        common_data["product_code"] = self.get_product_code(soup)
        common_data["gender"] = self.get_gender(soup)
        common_data["currency"] = "USD"
        common_data["price"] = price
        categories = self.get_categories(soup)
        common_data = self.insert_categories(common_data, categories)
        return common_data

    def get_name(self, soup):
        return soup["styles"][0]["product_variants"][0]["display_name"]

    def get_brand(self, soup):
        return soup["styles"][0]["trait"]["brands"][0]["display_name"]

    def get_sku_(self, soup):
        return soup["styles"][0]["code"]

    def get_product_code(self, soup):
        return soup["styles"][0]["code"]

    def get_gender(self, soup):
        return soup["styles"][0]["trait"]["genders"][0]["display_name"]

    def get_categories(self, soup):
        return [category["display_name"] for category in soup["styles"][0]["categories"]]

    def get_price(self, soup):
        return soup["styles"][0]["price"]["price_min"]

    def get_variant_data(self, soup):
        variant_data = []
        styles = soup["styles"][0]
        variants_products = styles["product_variants"]
        for variant in variants_products:
            size_list = self.get_size_list(variant)
            if len(size_list) == 0:
                logger.warning(f"no size {self.get_sku_(soup)}")
                continue
            size_str = self.size(size_list)
            record = {
                "key": f"{self.get_product_code(soup)}#{self.get_product_code2(variant)}",
                "color": self.get_color(variant),
                "size": size_str,
                "sale_price": self.get_sale_price(variant),
                "product_code2": self.get_product_code2(variant),
            }
            record = self.insert_images(record, self.get_image_urls(variant), 1)
            variant_data.append(record)
        return variant_data

    def get_product_code2(self, variant):
        return variant["code"]

    def get_size_list(self, variant):
        product_skus = variant["product_skus"]
        size_list = []
        for sku in product_skus:
            if not self.get_stock(sku):
                continue
            if "size" not in sku["trait"]:
                continue
            size_code = sku["trait"]["size"]["display_name"]
            dimension_code = sku["trait"].get("dimension")
            if dimension_code:
                size_list.append(size_code + "-" + dimension_code["display_name"])
            else:
                size_list.append(size_code)
        return size_list

    def get_stock(self, sku):
        stock = sku["inventory"]
        if stock == {} or stock["available_to_promise"] == 0:
            return False
        return True

    def get_color(self, variant):
        product_skus = variant["product_skus"]
        return product_skus[0]["trait"]["color"]["display_name"]

    def get_sale_price(self, variant):
        return variant["product_skus"][0]["price"]["actual_price"]

    def get_image_urls(self, variant):
        return [image["site_url"] for image in variant["asset"]["images"]]
