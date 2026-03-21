# YouTube 完全自動化システム

YouTube動画の**構想 → 原稿 → TTS音声 → 動画合成 → 投稿**を完全自動化し、
複数チャンネルのパフォーマンスを監視して**最も伸びているチャンネルに自動でリソースを集中**するシステムです。

---

## 機能概要

| 機能 | 説明 |
|------|------|
| **完全自動投稿** | GitHub Actions のcronで毎日09:00・21:00 JST に自動実行 |
| **コンテンツライブラリ** | 事前作成した原稿をスロット管理し順番に投稿（Anthropic API不要） |
| **AI原稿生成** | Claude API でトピック・ナレーション原稿を生成（Long form用） |
| **日本語TTS** | Google Cloud TTS WaveNet で高品質な日本語音声合成（1.5倍速） |
| **動画素材収集** | Pexels / Pixabay から無料動画素材を自動取得 |
| **ASS字幕アニメーション** | 左→右ワイプアニメーション付きオレンジ太字字幕を焼き込み |
| **サムネイル生成** | FFmpeg + ImageMagick でサムネイルを自動生成 |
| **マルチアカウント** | 最大5チャンネルを1つのリポジトリで管理 |
| **自動リバランス** | 週次でパフォーマンスをスコアリングし投稿頻度を自動調整 |
| **ダッシュボード** | GitHub Pages でリアルタイムに全チャンネルの状況を確認 |

---

## コンテンツ構成

現在のテーマは**心理学**です。

### Shorts（毎日2本 × 5日分 = 10スロット）

| スロット | タイトル |
|----------|---------|
| day01_run1 | 返報性の法則：試食したら買いたくなる理由 |
| day01_run2 | ダニング・クルーガー効果：無知な人ほど自信満々な理由 |
| day02_run1 | 認知的不協和：脳が都合の悪い事実を消す仕組み |
| day02_run2 | 吊り橋効果：ドキドキを恋と勘違いする脳の錯覚 |
| day03_run1 | 同調圧力：間違いとわかっていても従ってしまう心理 |
| day03_run2 | 損失回避バイアス：損は得より2倍痛い理由 |
| day04_run1 | プラシーボ効果：信じるだけで体が変わる科学 |
| day04_run2 | 先延ばし癖の正体：やる気を待ってはいけない理由 |
| day05_run1 | マジカルナンバー7：人間の記憶の限界と活用法 |
| day05_run2 | 感情と脳：怒りが判断力を破壊するメカニズム |

### Long form（コンテンツライブラリ）

| フォルダ | タイトル |
|----------|---------|
| chatgpt_work | 人間関係を変える行動心理学7つの法則 |
| smartphone_tips | 認知バイアス入門：判断を歪める10の心理トリック |

> 10スロット使い切ったら `assets/scripts/shorts/.run_counter` を `0` にリセットし、原稿を入れ替えて再利用します。

---

## セットアップ手順

### Step 1: Google Cloud の準備

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. **Text-to-Speech API** を有効化
3. **YouTube Data API v3** を有効化
4. **YouTube Analytics API** を有効化
5. サービスアカウントを作成し、JSONキーをダウンロード → base64エンコード
   ```bash
   base64 -i service_account.json | tr -d '\n'
   ```

### Step 2: YouTube OAuth トークンの取得

各チャンネルごとに一度だけ手動認証が必要です。

```bash
# ローカルで実行（チャンネルのGoogleアカウントでログイン）
pip install google-auth-oauthlib
python scripts/get_oauth_token.py --account-id account_01
# → ブラウザが開くので認証 → refresh_token が表示される
```

### Step 3: GitHub Secrets の設定

GitHub リポジトリの **Settings > Secrets and variables > Actions** で設定:

```
# 共有シークレット
ANTHROPIC_API_KEY        # Anthropic Console から取得（Long form のみ必要）
GCP_CREDENTIALS_JSON     # base64エンコードしたサービスアカウントJSON
PEXELS_API_KEY           # https://www.pexels.com/api/ から無料取得
PIXABAY_API_KEY          # https://pixabay.com/api/docs/ から無料取得
GH_PAT                   # GitHub > Settings > Developer settings > PAT (repo:write)
                         # ※ Shorts カウンター自動更新に必要

# アカウントごと（各チャンネル × 3）
YOUTUBE_REFRESH_TOKEN_ACCT01
YOUTUBE_CLIENT_ID_ACCT01
YOUTUBE_CLIENT_SECRET_ACCT01
# ... ACCT02〜ACCT05 も同様
```

### Step 4: アカウント設定

1. `config/accounts/account_01.yaml` の `channel_id` を実際のYouTubeチャンネルIDに変更
2. `config/accounts/accounts_registry.yaml` でアカウントを `enabled: true` に設定
3. `assets/fonts/` に `NotoSansCJK-Regular.ttf` を配置（字幕描画に必要）
4. `assets/bgm/` にBGM音源（`.mp3`）を配置

### Step 5: GitHub Pages の有効化

**Settings > Pages > Source** で `GitHub Actions` を選択

### Step 6: 動作テスト

```bash
# ローカルテスト（投稿なし）
pip install -r requirements.txt
python scripts/main.py --account-id account_01 --dry-run

# GitHub Actions 手動実行
# Actions タブ → "Upload Shorts Daily - account_01" → "Run workflow"
# → dry_run: チェックなし で実行
```

---

## ファイル構成

```
.
├── .github/workflows/
│   ├── upload_shorts_daily.yml   # Shorts専用：毎日2回自動実行（09:00/21:00 JST）
│   ├── upload_account.yml        # 再利用可能コアワークフロー（Long form）
│   ├── upload_account_01.yml     # チャンネル01スケジュール（自動生成）
│   ├── upload_account_02〜05.yml # チャンネル02〜05スケジュール（自動生成）
│   ├── collect_analytics.yml     # 日次Analytics収集
│   ├── rebalance.yml             # 週次リバランス
│   └── deploy_dashboard.yml      # GitHub Pages更新
├── config/
│   ├── genres.yaml               # ジャンル定義
│   ├── settings.yaml             # グローバル設定（TTS・字幕・動画品質など）
│   └── accounts/
│       ├── accounts_registry.yaml
│       └── account_01〜05.yaml
├── scripts/
│   ├── main.py                   # パイプライン統括（サブプロセス方式）
│   ├── 01_concept_generator.py   # トピック生成（AI）
│   ├── 02_script_writer.py       # 原稿生成（AI）
│   ├── 03_tts_generator.py       # 音声合成（Google TTS / 1.5倍速）
│   ├── 04_media_collector.py     # 動画素材収集（Pexels/Pixabay）
│   ├── 05_video_assembler.py     # 動画合成（ASS字幕アニメーション付き）
│   ├── 06_thumbnail_creator.py   # サムネイル生成
│   ├── 07_youtube_uploader.py    # YouTube投稿
│   ├── 08_config_loader.py       # 設定読み込み・認証情報解決
│   ├── 09_analytics_collector.py # Analytics収集
│   ├── 10_performance_scorer.py  # スコアリング・リバランス・cron自動生成
│   ├── 11_dashboard_builder.py   # summary.json生成
│   └── utils.py                  # 共通ユーティリティ
├── assets/
│   ├── fonts/                    # Noto Sans CJK フォント（字幕描画用）
│   ├── bgm/                      # BGM音源 (.mp3) を配置
│   └── scripts/
│       ├── shorts/               # Shorts コンテンツライブラリ
│       │   ├── .run_counter      # 次回実行スロット番号（0〜9）
│       │   ├── day01_run1/       # concept_shorts.json + script_shorts.json
│       │   ├── day01_run2/
│       │   │   ...（day05_run2 まで10スロット）
│       └── long/                 # Long form コンテンツライブラリ
│           ├── chatgpt_work/     # concept.json + script.json
│           └── smartphone_tips/
├── dashboard/
│   ├── index.html                # GitHub Pagesダッシュボード
│   ├── styles.css
│   └── app.js
├── data/metrics/                 # 自動生成されるメトリクスJSON
└── requirements.txt
```

---

## Shorts ワークフローの仕組み

### 自動実行スケジュール

| 実行時刻 | cron（UTC） |
|---|---|
| 毎日 09:00 JST | `0 0 * * *` |
| 毎日 21:00 JST | `0 12 * * *` |

### 3ジョブ構成

```
prepare ──→ upload ──→ increment
（スロット決定）  （動画生成・投稿）  （カウンター+1 & git commit）
```

1. **prepare**: `.run_counter` を読み、次のスロット（`day01_run1` 〜 `day05_run2`）を決定
2. **upload**: コンテンツライブラリの原稿を使って動画生成・YouTube投稿（Anthropic API不使用）
3. **increment**: 投稿成功時のみカウンターを+1してリポジトリにコミット（`[skip ci]` タグで再実行防止）

> カウンターが10に達するとエラーで停止。原稿を補充後に `.run_counter` を `0` にリセットして再開。

### 手動実行オプション

| オプション | 説明 |
|---|---|
| `dry_run: true` | 動画生成のみ・YouTube投稿なし・カウンター更新なし |
| `topic: day02_run1` | 指定スロットを強制実行（カウンター更新なし） |

---

## 字幕仕様

| 項目 | 設定値 |
|---|---|
| フォーマット | ASS（Advanced SubStation Alpha） |
| アニメーション | 左→右ワイプ（`\clip` + `\t()` タグ、600ms） |
| 文字色 | オレンジ `#FF6600` |
| アウトライン | 黒 3px |
| シャドウ | 1px |
| 太字 | あり |
| フォント | Noto Sans CJK JP |

`config/settings.yaml` の `subtitle:` セクションで変更可能です。

---

## コスト目安（月次）

| サービス | コスト |
|---------|-------|
| Anthropic Claude API | $0（Shortsはライブラリ使用のため不要） |
| Google Cloud TTS | $0（無料枠500万文字/月） |
| Pexels / Pixabay | $0（完全無料） |
| GitHub Actions | $0（publicリポジトリは無制限） |
| YouTube API | $0（無料クォータ内） |
| GitHub Pages | $0 |
| **合計** | **$0/月**（Shorts運用のみの場合） |

---

## ダッシュボード

GitHub Pages で毎朝自動更新されるダッシュボードで全チャンネルの状況を確認できます。

- **スコアランキング**: 全チャンネルのパフォーマンス順位
- **比較チャート**: 視聴数・登録者増減・CTRの横並び比較
- **30日トレンド**: 各チャンネルの成長推移
- **詳細テーブル**: 全メトリクスの数値確認

---

## リバランスの仕組み

毎週月曜 08:00 UTC に自動実行されるリバランサーが以下を行います:

1. 過去7日・30日のAnalyticsを集計
2. 複合スコアを計算（登録者40% + 視聴数25% + CTR20% + 視聴率15%）
3. 順位に応じて投稿頻度を更新:
   - **1位**: 週5本（リソース最大投入）
   - **2位**: 週3本
   - **3位以下**: 週1本（テスト継続）
4. `upload_account_XX.yml` の cron を自動再生成・コミット
