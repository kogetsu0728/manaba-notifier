# manaba-notifier

筑波大学manabaの「未提出の課題一覧」を確認し、Discord WebhookとTodoistに通知します。

認証画面やmanabaのHTML構造が変更されると動作しなくなる可能性があります。

## 主な機能

- 期限が近い未提出課題をDiscordに通知
- 新しく一覧に現れた課題をDiscordに通知
- 新着課題をTodoistに追加し、変更・完了・再出現を同期

## 動作環境

- Ubuntu server
- Python 3.12以上
- [uv](https://docs.astral.sh/uv/)
- Chromiumを実行できる環境

## セットアップ

```bash
git clone https://github.com/kogetsu0728/manaba-notifier.git
cd manaba-notifier
uv sync --frozen
uv run playwright install --with-deps chromium
cp .env.example .env
chmod 600 .env
```

`.env`にmanaba, Discord, Todoistの設定を記入します。必要な変数と既定値は[`.env.example`](.env.example)を参照してください。

```env
MANABA_ID=...
MANABA_PASSWORD=...
DEADLINE_ASSIGNMENTS_DISCORD_WEBHOOK_URL=...
NEW_ASSIGNMENTS_DISCORD_WEBHOOK_URL=...
TODOIST_API_TOKEN=...
TODOIST_PROJECT_ID=...
```

Ubuntuへの詳細な導入、Webhookの準備、systemd登録、更新、トラブル対応は[INSTALL.md](INSTALL.md)にまとめています。

## 実行

期限が近い課題を通知します。

```bash
uv run python -m manaba_notifier.main
```

新着課題を通知し、Todoistと同期します。

```bash
uv run python -m manaba_notifier.new_assignments_main
```

初回の新着通知では、現在表示されている未提出課題をすべて新着として扱います。新着同期の状態は次の場所に保存されます。

```txt
~/.local/state/manaba-notifier/new-assignments.json
```

## 通知の動作

期限通知は、締切が現在から`NOTIFY_WITHIN_DAYS`日以内にある未提出課題を期限順に送ります。期限切れと期限なしの課題は対象外です。

新着通知は、直前の一覧になく現在の一覧にある課題を送ります。一覧から消えた課題はTodoistで完了にし、再出現した場合は同じタスクを再開します。新着がない回はDiscordへ投稿しません。
