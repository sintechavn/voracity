import random
from enum import IntEnum
from typing import Any

import polars as pl
from prettytable import PrettyTable
from pydantic import BaseModel

from voracity2.models.database import session
from voracity2.models.site import Site


class ProxyMode(IntEnum):
    DIRECT_ONLY = 1
    PREFER_DIRECT = 2
    PROXY_ONLY = 3


class HttpResponse(BaseModel):
    url: str
    content: bytes
    text: str
    status_code: int
    headers: dict
    cookies: dict
    encoding: str = "utf-8"
    reason: str
    ok: bool


class Status(IntEnum):
    PENDING = 0
    RUNNING = 1
    END_OK = 2
    END_ERROR = 99


class Result(BaseModel):
    code: int
    message: str
    data: Any = None


class ResultDict(BaseModel):
    code: int
    message: str
    data: dict = {}


class ResultList(BaseModel):
    code: int
    message: str
    data: list[dict] = []


def generate_random_us_location() -> tuple[float, float]:
    """
    ランダムなUSAの緯度と経度を生成します。

    Returns:
        tuple: (latitude, longitude) の形式で緯度と経度を返します。
    """
    # アメリカ本土の緯度と経度の範囲
    lat_min, lat_max = 24.396308, 49.384358  # 緯度の範囲（南から北）
    lon_min, lon_max = -125.0, -66.93457  # 経度の範囲（西から東）

    latitude = random.uniform(lat_min, lat_max)
    longitude = random.uniform(lon_min, lon_max)

    return latitude, longitude


def dicts_to_pretty_table(data: list[dict]) -> str:
    headers = data[0].keys()
    rows = [row.values() for row in data]

    table = PrettyTable()
    table.field_names = headers
    table.add_rows(rows)

    return table.get_string()


def dicts_to_mrkdwn_table(data: list[dict]) -> str:
    df = pl.from_dicts(data)

    headers = df.columns
    rows = df.rows()

    # カラムごとの最大幅を計算（カラム名とデータ両方から）
    col_widths = [
        max(len(str(header)), max(len(str(cell)) for cell in col))
        for header, col in zip(headers, df.to_numpy().T)
    ]

    # ヘッダー行
    header_line = (
        "| "
        + " | ".join(f"{str(header).ljust(width)}" for header, width in zip(headers, col_widths))
        + " |"
    )
    separator_line = "|" + "|".join("-" * (width + 2) for width in col_widths) + "|"

    # データ行
    data_lines = [
        "| "
        + " | ".join(f"{str(cell).ljust(width)}" for cell, width in zip(row, col_widths))
        + " |"
        for row in rows
    ]

    # mrkdwn形式にまとめる
    return "```\n" + "\n".join([header_line, separator_line] + data_lines) + "\n```"


def get_site_name(site_id: int) -> str | None:
    """
    Get the site name based on the site ID.
    """
    ret = session.query(Site.site_name).filter(Site.id == site_id).first()
    if ret:
        return ret.site_name
    else:
        return None


def get_site_id(site_name: str) -> int | None:
    """
    Get the site ID based on the site name.
    """
    ret = session.query(Site.id).filter(Site.site_name == site_name).first()
    if ret:
        return ret.id
    else:
        return None
