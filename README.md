# YouTube 完全自動化システム

YouTube動画の**構想 → 原稿 → TTS音声 → 動画合成 → 投稿**を完全自動化し、
複数チャンネルのパフォーマンスを監視して**最も伸びているチャンネルに自動でリソースを集中**するシステムです。

---

## 機能概要

| 機能 | 説明 |
|------|------|
| **完全自動投稿** | GitHub Actions のcronで指定曜日・時刻に自動実行 |
| **AI原稿生成** | Claude API でジャンルに合わせたトピック・ナレーション原稿を生成 |
| **日本語TTS** | Google Cloud TTS WaveNet で高品質な日本語音声合成 |
| **動画素材収集** | Pexels / Pixabay から無料動画素材を自動取得 |
| **動画合成** | FFmpeg で動画+音声+日本語字幕を合成 |
| **サムネイル生成** | FFmpeg + ImageMagick でサムネイルを自動生成 |
| **マルチアカウント** | 最大5チャンネルを1つのリポジトリで管理 |
| **自動リバランス** | 週次でパフォーマンスをスコアリングし投稿頻度を自動調整 |
| **ダッシュボード** | GitHub Pages でリアルタイムに全チャンネルの状況を確認 |

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
ANTHROPIC_API_KEY        # Anthropic Console から取得
GCP_CREDENTIALS_JSON     # base64エンコードしたサービスアカウントJSON
PEXELS_API_KEY           # https://www.pexels.com/api/ から無料取得
PIXABAY_API_KEY          # https://pixabay.com/api/docs/ から無料取得
GH_PAT                   # GitHub > Settings > Developer settings > PAT (repo:write)

# アカウントごと（各チャンネル × 3）
YOUTUBE_REFRESH_TOKEN_ACCT01
YOUTUBE_CLIENT_ID_ACCT01
YOUTUBE_CLIENT_SECRET_ACCT01
# ... ACCT02〜ACCT05 も同様
```

### Step 4: アカウント設定

1. `config/accounts/account_01.yaml` の `channel_id` を実際のYouTubeチャンネルIDに変更
2. `config/accounts/accounts_registry.yaml` でアカウントを `enabled: true` に設定
3. `config/genres.yaml` でジャンルを確認・カスタマイズ

### Step 5: GitHub Pages の有効化

**Settings > Pages > Source** で `GitHub Actions` を選択

### Step 6: 動作テスト

```bash
# ローカルテスト（投稿なし）
pip install -r requirements.txt
python scripts/main.py --account-id account_01 --dry-run

# GitHub Actions 手動実行
# Actions タブ → "Upload - account_01" → "Run workflow" → dry_run: true
```

---

## ファイル構成

```
.
├── .github/workflows/
│   ├── upload_account.yml        # 再利用可能コアワークフロー
│   ├── upload_account_01.yml     # チャンネル01スケジュール
│   ├── upload_account_02〜05.yml # チャンネル02〜05スケジュール
│   ├── collect_analytics.yml     # 日次Analytics収集
│   ├── rebalance.yml             # 週次リバランス
│   └── deploy_dashboard.yml      # GitHub Pages更新
├── config/
│   ├── genres.yaml               # ジャンル定義
│   ├── settings.yaml             # グローバル設定
│   └── accounts/
│       ├── accounts_registry.yaml
│       └── account_01〜05.yaml
├── scripts/
│   ├── main.py                   # パイプライン統括
│   ├── 01_concept_generator.py   # トピック生成
│   ├── 02_script_writer.py       # 原稿生成
│   ├── 03_tts_generator.py       # 音声合成
│   ├── 04_media_collector.py     # 動画素材収集
│   ├── 05_video_assembler.py     # 動画合成
│   ├── 06_thumbnail_creator.py   # サムネイル生成
│   ├── 07_youtube_uploader.py    # YouTube投稿
│   ├── 08_config_loader.py       # 設定読み込み
│   ├── 09_analytics_collector.py # Analytics収集
│   ├── 10_performance_scorer.py  # スコアリング・リバランス
│   ├── 11_dashboard_builder.py   # summary.json生成
│   └── utils.py                  # 共通ユーティリティ
├── dashboard/
│   ├── index.html                # GitHub Pagesダッシュボード
│   ├── styles.css
│   └── app.js
├── data/metrics/                 # 自動生成されるメトリクスJSON
├── assets/
│   ├── fonts/                    # Noto Sans CJK フォント
│   └── bgm/                      # BGM音源 (.mp3) を配置
└── requirements.txt
```

---

## コスト目安（月次）

| サービス | コスト |
|---------|-------|
| Anthropic Claude API | ~$5-15 |
| Google Cloud TTS | $0（無料枠500万文字/月） |
| Pexels / Pixabay | $0（完全無料） |
| GitHub Actions | $0（publicリポジトリは無制限） |
| YouTube API | $0（無料クォータ内） |
| GitHub Pages | $0 |
| **合計** | **$5-15/月** |

---

## ダッシュボード

GitHub Pages で毎朝自動更新されるダッシュボードで全チャンネルの状況を確認できます。

- **スコアランキング**: 全チャンネルのパフォーマンス順位
- **比較チャート**: 視聴数・登録者増減・CTRの横並び比較
- **30日トレンド**: 各チャンネルの成長推移
- **詳細テーブル**: 全メトリクスの数値確認

---

## リバランスの仕組み

毎週月曜に自動実行されるリバランサーが以下を行います:

1. 過去7日・30日のAnalyticsを集計
2. 複合スコアを計算（登録者40% + 視聴数25% + CTR20% + 視聴率15%）
3. 順位に応じて投稿頻度を更新:
   - **1位**: 週5本（リソース最大投入）
   - **2位**: 週3本
   - **3位以下**: 週1本（テスト継続）
4. `config/accounts/*.yaml` とGitHub Actionsワークフローを自動更新
