import os
from contextlib import contextmanager

from dotenv import load_dotenv
from flask import Flask, render_template, request
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# .envファイルを読み込み
load_dotenv()

from voracity2.lib.job import get_job_progress
from voracity2.models.database import engine
from voracity2.models.proxy import Proxy

app = Flask(__name__)


@contextmanager
def get_db_session():
    """データベースセッションのコンテキストマネージャー"""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.route("/")
def index():
    return render_template("index.j2")


@app.route("/job/progress")
def job_progress():
    status = get_job_progress()
    return render_template("job_progress.j2", status=status)


@app.route("/proxy/status")
def proxy_status():
    with get_db_session() as session:
        stmt = text("select * from v_proxy_status3")
        proxies = [dict(row) for row in session.execute(stmt).mappings()]

    return render_template("proxy_status.j2", proxies=proxies)


@app.route("/proxy/status/<group_name>")
def proxy_status_detail(group_name: str):
    with get_db_session() as session:
        proxies = session.query(Proxy).filter(Proxy.group_name == group_name).all()

    return render_template("proxy_status_detail.j2", proxies=proxies, group_name=group_name)


@app.route("/crawl_logs")
def crawl_logs():
    with get_db_session() as session:
        site_name = request.args.get("site_name", "")
        page = int(request.args.get("page", 1))
        per_page = 50
        offset = (page - 1) * per_page

        # サイト名の一覧を取得（フィルタ用）
        site_names_query = session.execute(
            text("SELECT DISTINCT site_name FROM crawl_logs ORDER BY site_name")
        )
        site_names = [row[0] for row in site_names_query]

        # 総件数を取得
        if site_name:
            count_query = session.execute(
                text("SELECT COUNT(*) FROM crawl_logs WHERE site_name = :site_name"),
                {"site_name": site_name},
            )
        else:
            count_query = session.execute(text("SELECT COUNT(*) FROM crawl_logs"))

        total_count = count_query.scalar()
        total_pages = (total_count + per_page - 1) // per_page

        # crawl_logsのデータを取得（ページング付き）
        if site_name:
            logs_query = session.execute(
                text(
                    "SELECT * FROM crawl_logs WHERE site_name = :site_name ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"site_name": site_name, "limit": per_page, "offset": offset},
            )
        else:
            logs_query = session.execute(
                text(
                    "SELECT * FROM crawl_logs ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": per_page, "offset": offset},
            )

        logs = [dict(row) for row in logs_query.mappings()]

    return render_template(
        "crawl_logs.j2",
        logs=logs,
        site_names=site_names,
        selected_site=site_name,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count,
        per_page=per_page,
    )


if __name__ == "__main__":
    # 環境変数から設定を取得
    debug_mode = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes", "on")
    port = int(os.getenv("FLASK_PORT", "5000"))
    host = os.getenv("FLASK_HOST", "0.0.0.0")

    print(f"Starting Voracity2 Flask app on {host}:{port} (debug={debug_mode})")
    app.run(debug=debug_mode, host=host, port=port)
