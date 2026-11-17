# Voracity2 UI

Voracity2 WebクローラーのWeb管理インターフェース

## 機能

- ジョブ進捗監視
- プロキシ状況確認
- クロール履歴閲覧
- レスポンシブデザイン対応

## 起動方法

### 基本起動
```bash
cd d:\proj\voracity2
uv run python src/voracity2/ui/app.py
```

### 環境変数での設定

以下の環境変数で動作を制御できます：

| 環境変数 | デフォルト値 | 説明 |
|---------|-------------|------|
| `FLASK_DEBUG` | `True` | デバッグモード (True/False, 1/0, yes/no, on/off) |
| `FLASK_PORT` | `5000` | ポート番号 |
| `FLASK_HOST` | `0.0.0.0` | ホストアドレス |

### 使用例

#### 本番環境モード（デバッグ無効）
```powershell
$env:FLASK_DEBUG="False"; uv run python src/voracity2/ui/app.py
```

#### カスタムポートで起動（推奨: 5001番）
```powershell
$env:FLASK_PORT="5001"; uv run python src/voracity2/ui/app.py
```

#### 外部アクセス許可
```powershell
$env:FLASK_HOST="0.0.0.0"; $env:FLASK_PORT="5001"; uv run python src/voracity2/ui/app.py
```

#### 複数設定の組み合わせ
```powershell
$env:FLASK_DEBUG="False"; $env:FLASK_PORT="5001"; $env:FLASK_HOST="0.0.0.0"; uv run python src/voracity2/ui/app.py
```

### .envファイルでの設定

プロジェクトルートの`.env`ファイルで設定を管理できます：

```bash
# Flask UI設定
FLASK_DEBUG=True
FLASK_PORT=5001
FLASK_HOST=0.0.0.0
```

.envファイルの設定は環境変数よりも優先度が低いため、一時的な変更は環境変数で上書き可能です。

## アクセス

起動後、ブラウザで以下にアクセス：
- http://127.0.0.1:5000 （デフォルト）
- http://127.0.0.1:5001 （推奨）
- 設定したホスト:ポート

## レスポンシブデザイン

- **PC（992px以上）**: テーブル表示
- **タブレット（768px-991px）**: カード表示（2列）
- **スマホ（767px以下）**: カード表示（1列）

## maverickとの併用

maverickとvoracity2を同時に起動する場合は、異なるポート番号を設定してください：

- Maverick: ポート5000
- Voracity2: ポート5001

```powershell
# Maverick (ポート5000)
cd d:\proj\maverick
uv run python maverick/ui/app.py

# Voracity2 (ポート5001) - 別ターミナルで実行
cd d:\proj\voracity2
$env:FLASK_PORT="5001"; uv run python src/voracity2/ui/app.py
```