import importlib

import click

from voracity2 import settings
from voracity2.lib import utils
from voracity2.scraper.base import BaseScraper

logger = settings.logger


def scrape(
    site: str,
    target: str,
    proxy_group_name: str,
) -> None:
    """
    Scrape page data from site
        sites: bc, dicks, endclothing, kohls, yoox_men, yoox_women
        target: page, item
    """
    module_path = f"voracity2.scraper.{site}"
    class_name = f"{site.capitalize()}Scraper"
    scraper_class = getattr(importlib.import_module(module_path), class_name)

    options = {
        "proxy_group_name": proxy_group_name if proxy_group_name else site,
        "block_images": True,
    }
    scraper: BaseScraper = scraper_class(options=options)

    method = getattr(scraper, f"crawl_{target}", None)
    if method:
        method()
    else:
        raise NotImplementedError(f"Method 'crawl' not implemented in {scraper_class}")


@click.command()
@click.argument("site_name")
@click.argument("target")
@click.option("-g", "--proxy-group-name", "proxy_group_name", help="proxy group name")
def scrape_one_command(
    site_name: str,
    target: str,
    proxy_group_name: str,
) -> None:
    """
    Command to scrape a specific site and target with optional proxy settings.
    """
    site_id = utils.get_site_id(site_name)
    if not site_id:
        msg = f"Invalid site name: {site_name}. Please check the site name and try again."
        logger.error(msg)
        return

    # crawl_page
    scrape(site_name, target, proxy_group_name)
