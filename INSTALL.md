# Ubuntuへの導入と運用

この文書では、`manaba-notifier` を常時起動しているUbuntu serverへ導入し、systemd timerで運用する手順を説明します。

このツールは自分自身の筑波大学 manaba アカウントでのみ使用してください。`.env`、Cookie、Webhook URL、Todoist tokenをGit、ログ、Issueへ含めないでください。

## 1. 前提

必要なものは以下です。

- systemdが動作するUbuntu server
- Python 3.12以上
- `git`、`curl`、`uv`
- 筑波大学 manaba の利用者IDとパスワード
- 期限通知用と新着通知用のDiscord Webhook
- Todoist API tokenと同期先プロジェクトID

基本ツールがない場合は導入します。

```bash
sudo apt update
sudo apt install -y git curl ca-certificates
```

`uv` は[公式手順](https://docs.astral.sh/uv/getting-started/installation/)に従って導入します。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. リポジトリと依存関係

```bash
git clone https://github.com/kogetsu0728/manaba-notifier.git
cd manaba-notifier
uv sync --frozen
uv run playwright install chromium
```

ChromiumのOS依存ライブラリが不足する場合は、次を実行します。

```bash
uv run playwright install --with-deps chromium
```

このコマンドはOSパッケージの導入に `sudo` を必要とする場合があります。

## 3. 外部サービスの準備

Discordで期限通知用と新着通知用のWebhookを1個ずつ作成します。Webhook URLを知っている人は投稿できるため、外部へ共有しないでください。

Todoistでは課題同期専用のプロジェクトを作成し、[Integrations settings](https://app.todoist.com/app/settings/integrations/developer) からPersonal API tokenを取得します。プロジェクトURLなどから同期先のプロジェクトIDも確認します。

## 4. 環境変数

サンプルから `.env` を作成し、所有者だけが読めるようにします。

```bash
cp .env.example .env
chmod 600 .env
```

以下の必須項目を設定します。

```env
MANABA_LOGIN_URL=https://manaba.tsukuba.ac.jp/ct/login
MANABA_ASSIGNMENTS_URL=https://manaba.tsukuba.ac.jp/ct/home_library_query

MANABA_ID=...
MANABA_PASSWORD=...

DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL=...
NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL=...
TODOIST_API_TOKEN=...
TODOIST_PROJECT_ID=...

NOTIFY_WITHIN_DAYS=3
NOTIFY_EMPTY=true
TIMEZONE=Asia/Tokyo

# CHROME_PATH=/usr/bin/chromium
```

| 変数 | 用途 |
| --- | --- |
| `NOTIFY_WITHIN_DAYS` | 期限通知の対象とする日数 |
| `NOTIFY_EMPTY` | 対象が0件でも期限通知を送るか |
| `TIMEZONE` | 課題期限の判定に使うタイムゾーン |
| `CHROME_PATH` | Playwright同梱Chromiumを使えない場合の実行ファイル |

`CHROME_PATH` は通常不要です。設定内容の一覧は [`.env.example`](.env.example) を参照してください。

## 5. 動作確認

まずテストを実行します。このテストはmanabaへアクセスしません。

```bash
uv run pytest
```

続いて、各CLIを1回ずつ手動実行します。

```bash
uv run python -m manaba_notifier.main
uv run python -m manaba_notifier.new_assignments_main
```

初回の新着通知では、現在の未提出課題がすべて通知され、Todoistへ追加されます。短時間に繰り返し実行しないでください。

## 6. systemd serviceの調整

リポジトリ内のserviceファイルは公開用のテンプレートです。`@USER@` は実行ユーザー名、`@INSTALL_DIR@` はこのリポジトリの絶対パスに置き換えて使用します。次の登録手順で自動的に置き換えられるため、リポジトリ内のファイルを直接編集する必要はありません。

## 7. systemdへの登録

手動実行が成功してから登録します。

```bash
INSTALL_USER="$(id -un)"
INSTALL_DIR="$(pwd)"

sed -e "s|@USER@|${INSTALL_USER}|g" \
    -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
    systemd/manaba-notifier.service \
  | sudo tee /etc/systemd/system/manaba-notifier.service >/dev/null
sed -e "s|@USER@|${INSTALL_USER}|g" \
    -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
    systemd/manaba-new-assignments.service \
  | sudo tee /etc/systemd/system/manaba-new-assignments.service >/dev/null
sudo cp systemd/manaba-notifier.timer /etc/systemd/system/
sudo cp systemd/manaba-new-assignments.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

定義を検証します。

```bash
sudo systemd-analyze verify \
  /etc/systemd/system/manaba-notifier.service \
  /etc/systemd/system/manaba-notifier.timer \
  /etc/systemd/system/manaba-new-assignments.service \
  /etc/systemd/system/manaba-new-assignments.timer
```

timerを有効化します。

```bash
sudo systemctl enable --now manaba-notifier.timer
sudo systemctl enable --now manaba-new-assignments.timer
```

期限通知は毎日08:00 JST、新着通知は毎時00分と30分に実行されます。サーバー自体のタイムゾーンがUTCでも、timer側で `Asia/Tokyo` を指定しています。

```bash
systemctl list-timers manaba-notifier.timer --all
systemctl list-timers manaba-new-assignments.timer --all
```

## 8. systemd経由の確認

timerを待たずにserviceを1回実行できます。

```bash
sudo systemctl start manaba-notifier.service
sudo systemctl start manaba-new-assignments.service
```

状態とログを確認します。

```bash
systemctl status manaba-notifier.service --no-pager
systemctl status manaba-new-assignments.service --no-pager
journalctl -u manaba-notifier.service -n 100 --no-pager
journalctl -u manaba-new-assignments.service -n 100 --no-pager
```

`Type=oneshot` のため、正常終了後にserviceが `inactive (dead)` と表示されること自体は問題ありません。

失敗時の診断ログは次に保存されます。

```txt
~/.local/state/manaba-notifier/logs/deadline-errors.log
~/.local/state/manaba-notifier/logs/new-assignments-errors.log
```

診断ログには認証情報、Webhook URL、Todoist token、Cookie、課題内容、HTTP本文を保存しません。

## 更新

```bash
cd /path/to/manaba-notifier
git pull --ff-only
uv sync --frozen
uv run playwright install chromium
uv run pytest
```

systemd定義が変更された場合だけ、「7. systemdへの登録」の手順でserviceファイルを再生成し、timerも再配置して読み込み直します。

```bash
INSTALL_USER="$(id -un)"
INSTALL_DIR="$(pwd)"
sed -e "s|@USER@|${INSTALL_USER}|g" \
    -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
    systemd/manaba-notifier.service \
  | sudo tee /etc/systemd/system/manaba-notifier.service >/dev/null
sed -e "s|@USER@|${INSTALL_USER}|g" \
    -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
    systemd/manaba-new-assignments.service \
  | sudo tee /etc/systemd/system/manaba-new-assignments.service >/dev/null
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart manaba-notifier.timer
sudo systemctl restart manaba-new-assignments.timer
```

## 停止と再開

```bash
# 停止
sudo systemctl disable --now manaba-notifier.timer
sudo systemctl disable --now manaba-new-assignments.timer

# 再開
sudo systemctl enable --now manaba-notifier.timer
sudo systemctl enable --now manaba-new-assignments.timer
```

## トラブルシューティング

### 必須環境変数が設定されていない

`.env` の変数名と空欄を確認します。値を確認する際も、`.env` 全体をターミナルや外部サービスへ出力しないでください。

systemd経由だけ失敗する場合は、serviceの `EnvironmentFile` と実際の配置先が一致しているか確認します。

```bash
systemctl cat manaba-notifier.service
systemctl cat manaba-new-assignments.service
```

### Chromiumが起動しない

```bash
uv run playwright install --with-deps chromium
```

Playwright同梱Chromiumを利用できない環境では、システムのChromeまたはChromiumの絶対パスを `.env` の `CHROME_PATH` に設定します。

### ログインまたは課題取得に失敗する

利用者IDとパスワードを確認し、通常のブラウザからmanabaへログインできるか確認します。認証画面への多要素認証、CAPTCHA、同意画面の追加や、manabaのHTML変更でも失敗します。

短時間に何度も再実行せず、原因を確認してから1回だけ再試行してください。

### Discordへ届かない

期限通知と新着通知で、正しいWebhookを設定しているか確認します。Webhookが削除または再生成されている場合は `.env` を更新します。Webhook URL全体をログやIssueへ貼り付けないでください。

### timerが実行されない

```bash
systemctl is-enabled manaba-notifier.timer
systemctl is-enabled manaba-new-assignments.timer
systemctl list-timers manaba-notifier.timer --all
systemctl list-timers manaba-new-assignments.timer --all
```

無効な場合は「停止と再開」の手順で有効化します。

## 参考資料

- [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [Discord Webhooks](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)
