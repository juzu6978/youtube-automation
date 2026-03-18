# コンテンツライブラリ

Claude APIを使わずに動画を生成するための、事前作成済みコンテンツライブラリです。

## ディレクトリ構造

```
assets/scripts/
├── _template/          # テンプレートファイル（新規トピック作成時の参考）
│   ├── concept.json
│   ├── script.json
│   ├── concept_shorts.json
│   └── script_shorts.json
├── chatgpt_work/       # ChatGPTと仕事効率化
│   ├── concept.json        # 横型（landscape）用
│   ├── script.json         # 横型（landscape）用
│   ├── concept_shorts.json # 縦型（shorts/tiktok）用
│   └── script_shorts.json  # 縦型（shorts/tiktok）用
└── README.md
```

## 使い方

### GitHub Actions（手動実行）
1. Actions タブ → 「Upload - account_XX」を選択
2. 「Run workflow」をクリック
3. `topic` フィールドにディレクトリ名を入力（例: `chatgpt_work`）
4. `dry_run: true` にして動作確認
5. 問題なければ `dry_run: false` で本番投稿

### ローカル実行
```bash
# 横型動画
python scripts/main.py --account-id account_01 --topic chatgpt_work --dry-run

# Shorts動画
python scripts/main.py --account-id account_01 --topic chatgpt_work --format shorts --dry-run
```

## 新しいトピックの追加

1. `_template/` フォルダをコピーして新しいトピック名にリネーム
2. 各JSONファイルを編集（_template の説明コメントを参考に）
3. `concept.json` と `script.json` は必須、`concept_shorts.json` と `script_shorts.json` はオプション
4. Shorts/TikTok用ファイルがない場合、通常版にフォールバック

## ファイル仕様

### concept.json
```json
{
  "topic": "テーマ名",
  "hook": "フック（視聴者を引き込む一言）",
  "outline": [{"title": "セクション名", "keywords": ["英語キーワード"]}],
  "search_keywords": ["Pexels/Pixabay検索用キーワード"]
}
```

### script.json
```json
{
  "title": "YouTube動画タイトル",
  "description": "動画説明文",
  "tags": ["タグ"],
  "sentences": [{"text": "ナレーション文", "section": "セクション名", "index": 0}]
}
```
