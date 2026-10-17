# Yapboard

> Leaderboard for yappers.

A tiny passive Telegram bot that quietly counts group activity and shows a
native rich-message leaderboard on demand. Message text is never stored — only
aggregated counters and normalized word frequencies.

## Features

- Passive counting of messages, characters, media and replies (hourly aggregates).
- `/top` — striped table with period buttons (`Today · 7d · 30d · All`),
  metric buttons (`Messages · Characters · Media`) and pagination.
  Custom range: `/top 2026-09-01 2026-09-30`.
- `/words` — most used meaningful words, either in total or per member.
  English and Russian; stopwords, interjections and filler are filtered, and
  inflected forms are grouped. Disable with `WORD_STATS_ENABLED=false`.
- `/me` — personal card: ranks per period, peak hour, 14-day sparkline.
- `/hours` — time-of-day board; `/stats` — chat summary.
- Privacy: `/optout`, `/optin`, `/forgetme`. Admins: `/pause`, `/resume`, `/settings`.
- Rich Messages with a transparent HTML fallback (`RICH_ENABLED=false` forces it).

## Run with Docker

```bash
cp .env.example .env          # set BOT_TOKEN; disable privacy mode in @BotFather
docker compose up --build -d  # migrations run at startup
docker compose logs -f bot
```

## Local development

```bash
uv sync --all-groups
export DATABASE_URL=postgresql://hubbub@127.0.0.1:5432/hubbub
uv run python -m yapboard
```

## Tests

```bash
export TEST_DATABASE_URL=postgresql://hubbub@127.0.0.1:5432/hubbub_test
uv run pytest -q && uv run ruff check src tests && uv run mypy
```

## Configuration

Read from the environment / `.env` (see `.env.example`): `BOT_TOKEN`,
`DATABASE_URL`, `PAGE_SIZE`, `TOP_COOLDOWN_SEC`, `RICH_ENABLED`,
`WORD_STATS_ENABLED`, `DEFAULT_TZ`, `FLUSH_INTERVAL_SEC`, and optional
`WEBHOOK_*` for webhook mode.

## Layout

```
src/yapboard/   bot: handlers, collector, stats, wordstats, periods,
                render (rich + fallback), words (tokenizer & stopwords)
migrations/     001_init.sql, 002_word_counts.sql
tests/          unit, DB-integration and dispatcher flow tests
```

## Privacy

Only counters and aggregated word frequencies are stored — never message text,
word order or a link to individual messages. Word counts are kept per member
and per chat-local day. `/forgetme` deletes all your rows in the chat;
`/optout` stops counting you.
