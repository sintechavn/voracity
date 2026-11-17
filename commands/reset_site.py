from logging import getLogger

import click

from voracity2.lib import utils
from voracity2.models.category import Category
from voracity2.models.database import session
from voracity2.models.item import Item, ItemBackup
from voracity2.models.page_ import Page_

logger = getLogger(__name__)


def reset_category(site_id: int):
    session.query(Category).filter(Category.site_id == site_id, Category.status != 99).update(
        {"status": 0}
    )
    session.commit()


def delete_pages(site_id: int):
    session.query(Page_).filter(Page_.site_id == site_id).delete()
    session.query(Page_).filter(Page_.site_id == site_id + 900).delete()
    session.commit()


def delete_products(site_id: int):
    deleted_backup_count = session.query(ItemBackup).filter(ItemBackup.site_id == site_id).delete()
    products_to_backup = session.query(Item).filter(Item.site_id == site_id).all()
    
    if products_to_backup:
        # Copy each product to backup table
        backup_count = 0
        for product in products_to_backup:
            backup_item = ItemBackup(
                id=product.id,
                site_id=product.site_id,
                page_id=product.page_id,
                url=product.url,
                name=product.name,
                brand=product.brand,
                product_code=product.product_code,
                product_code2=product.product_code2,
                sku=product.sku,
                color=product.color,
                gender=product.gender,
                category1=product.category1,
                category2=product.category2,
                category3=product.category3,
                category4=product.category4,
                category5=product.category5,
                category6=product.category6,
                category7=product.category7,
                category8=product.category8,
                category9=product.category9,
                category10=product.category10,
                price=product.price,
                sale_price=product.sale_price,
                currency=product.currency,
                size=product.size,
                image1=product.image1,
                image2=product.image2,
                image3=product.image3,
                image4=product.image4,
                image5=product.image5,
                image6=product.image6,
                image7=product.image7,
                image8=product.image8,
                image9=product.image9,
                image10=product.image10,
                created_at=product.created_at,
                updated_at=product.updated_at,
                status=product.status,
                key=product.key,
                updated_by=product.updated_by,
                result_text=product.result_text,
                # backup_date will be auto-set to current timestamp
            )
            session.add(backup_item)
            backup_count += 1
        
        session.commit()
        logger.info(f"Backed up {backup_count} products to products_new_backup for site_id={site_id}")
    else:
        logger.info(f"No products found to backup for site_id={site_id}")
    
    # Step 3: Delete products from products_new
    deleted_count = session.query(Item).filter(Item.site_id == site_id).delete()
    session.commit()
    logger.info(f"Deleted {deleted_count} products from products_new for site_id={site_id}")

def reset_site(site_name: str) -> bool:
    site_id = utils.get_site_id(site_name)
    if not site_id:
        logger.error("Invalid site")
        return False

    logger.info(f"start cleanup: {site_id}:{site_name}")
    reset_category(site_id)
    delete_pages(site_id)
    delete_products(site_id)
    logger.info(f"cleanup done: {site_id}:{site_name}")

    return True


@click.command()
@click.argument("site_name")
def reset_site_command(site_name: str) -> None:
    """
    Command to reset site information.
    """

    reset_site(site_name)
