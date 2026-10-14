# PLAN — passive chat-activity leaderboard bot for Telegram

> Working title: **Hubbub** (see [Naming](#naming) for alternatives)
> Stack: Python 3.12 · aiogram 3.x · Telegram Bot API 10.x **Rich Messages** · PostgreSQL · Docker

---

## 1. Concept

A tiny bot that sits in a group chat, **silently counts activity** and shows a **beautiful leaderboard on demand** — for any period, switchable with buttons, rendered as a native Telegram *rich message* (real table, headings, button rows) instead of a wall of monospace text.

Inspired by Combot's analytics, but deliberately narrow:

| In scope | Out of scope (on purpose) |
|---|---|
| Passive counting of messages / chars / media | Moderation, bans, mutes, captcha |
| Leaderboards by period and metric | Anti-spam (CAS-style) |
| Personal card (`/me`), activity by hour | AI replies, anonymous questions |
| Privacy controls (opt-out, wipe data) | Storing message text — **never** |

**Design principles**

1. **Lightweight** — one process, one Postgres, no Redis, no queue. Runs on a 1 vCPU / 512 MB VPS.
2. **Passive** — zero noise in the chat. The bot speaks only when asked.
3. **Private by design** — counters only, no message text, easy opt-out and wipe.
4. **Pretty** — one message that edits itself in place; tables, bars, compact buttons.

---

## 2. What are Rich Messages (verified)

Rich Messages are a Telegram **Bot API 10.1** feature (released **11 June 2026**). Bots send structured content — headings, tables, nested lists, collapsible sections, block quotes, math, inline media — via the new method `sendRichMessage`. Up to ~32k characters per message (long ones get a "Show more" fold).

Timeline from the official changelog:

| Bot API | Date | Rich Messages changes |
|---|---|---|
| 10.1 | 2026-06-11 | `sendRichMessage`, `sendRichMessageDraft` (streaming), `InputRichMessage` (`html` / `markdown` / `blocks`), `rich_message` param in `editMessageText`, `InputRichMessageContent` for inline results |
| 10.2 | 2026-07-14 | `media` field on `InputRichMessage`, full `InputRichBlock*` builder set (paragraph, heading, table, list, details, photo, …) |
| 10.3 | 2026-08-24 | **Buttons inside rich messages** (`InputRichBlockButtons`, `RichMessageButton`), `is_compact` for tables, expandable block quotes, document blocks, ephemeral messages |

**What matters for us**

- `InputRichMessage` takes **exactly one** of `html`, `markdown` or `blocks`.
- `InputRichBlockTable`: `cells: list[list[RichBlockTableCell]]`, `is_bordered`, `is_striped`, `is_compact`, `caption`. A cell has `align`, `valign`, `text`, `is_header`, `colspan`, `rowspan`.
- `InputRichBlockButtons`: 1–8 buttons per row block, `align` = left / center / right.
- `RichMessageButton`: `text`, `style` (`primary` / `success` / `danger` / `link`), and exactly one action: `callback_data` (1–64 bytes), `url`, `web_app`, `copy_text`, `switch_inline_query*`, `disabled`, …
- Editing in place: `editMessageText(rich_message=...)`.
- **Inbound messages from users are still plain text** — rich messages are send-only. Counting logic is unaffected.
- aiogram: the 3.31.0 docs include `SendRichMessage`, `Message.answer_rich()` / `reply_rich()` and all types above. Pin `aiogram>=3.31`.

**Caveats to handle**

- Older Telegram clients may not render rich messages → keep a **plain-text fallback renderer** (HTML `parse_mode`) selected by a config flag / on API error.
- Not verified by me: exact behaviour in large supergroups and whether older clients degrade gracefully. Test early in a real group (Milestone 0).
- Confirm in aiogram docs whether table cell `text` accepts plain `str` or needs `RichText*` objects (type is `RichTextUnion`).

Sources: [Bot API changelog](https://core.telegram.org/bots/api-changelog), [aiogram `SendRichMessage`](https://docs.aiogram.dev/en/latest/api/methods/send_rich_message.html), [`InputRichMessage`](https://docs.aiogram.dev/en/latest/api/types/input_rich_message.html).

---

## 3. Features

### 3.1 MVP (v0.1)

- **Passive counter** for groups/supergroups: messages, characters, media (photo/video/voice/sticker/gif/document split), replies.
- **`/top`** — leaderboard as a rich message with:
  - period buttons: `Today · 7d · 30d · All`
  - metric buttons: `Messages · Chars · Media`
  - pagination: `‹ Prev · 1/3 · Next ›` (10 rows per page)
  - striped table: rank, user, value, share bar
- **`/me`** — personal card: rank, totals for each period, favourite hour, 14-day sparkline.
- **Privacy**: `/optout`, `/optin`, `/forgetme` (wipes the user's rows in this chat), admin `/pause` & `/resume` for the whole chat.
- **`/help`, `/start`**.

### 3.2 v0.2

- **Time-of-day boards**: Morning / Day / Evening / Night (in the chat's timezone) + "peak hour".
- **Custom date range**: `/top 2026-09-01 2026-09-30` and a "Pick dates" button (day pickers via buttons).
- **Chat timezone** setting (`/settings` — rich message with toggle buttons, admin only).
- **Chat summary** (`/stats`): totals, active users, busiest day, hour heatmap as a table with shaded cells.
- **Trend arrows** vs previous period (▲ ▼ =).

### 3.3 Later (only if it earns its place)

- Streaks and light achievements ("Night owl", "Wall of text").
- Weekly digest posted by schedule (opt-in, admin).
- Mini App / public web page with charts.
- Inline mode: `@bot top` in any chat.
- XP / levels / reputation (gamification — keep out until the core is loved).

---

## 4. UX of the leaderboard

One message, edited in place. Mock (rich message rendering, simplified):

```
🏆 Leaderboard · Last 7 days · Messages
──────────────────────────────────────────
 #   Member           Msgs    Share
 🥇  Alex             1 842   ▰▰▰▰▰▰▱▱  31%
 🥈  Masha              977   ▰▰▰▱▱▱▱▱  17%
 🥉  Dan                640   ▰▰▱▱▱▱▱▱  11%
 4   Kate               412   ▰▱▱▱▱▱▱▱   7%
 …
──────────────────────────────────────────
 5 912 messages · 38 active members · updated 21:04

 [ Today ] [ 7d ✓ ] [ 30d ] [ All ]
 [ Messages ✓ ] [ Chars ] [ Media ]
 [ ‹ ]   1 / 4   [ › ]
```

Block mapping:

| UI part | Rich block |
|---|---|
| Title + period + metric | `InputRichBlockSectionHeading` |
| Table of members | `InputRichBlockTable` (`is_striped`, `is_compact`, header row with `is_header=True`) |
| Summary line | `InputRichBlockFooter` |
| Period / metric / pager | up to 3 × `InputRichBlockButtons` (`align="center"`) |
| Per-section extras (hours heatmap, details) | `InputRichBlockDetails` (collapsible) |

Button states: the active option uses `style="primary"`, the rest default; pager edge buttons use `disabled`.

Callback data (≤ 64 bytes): `lb:<period>:<metric>:<page>` e.g. `lb:7d:msg:0`. Custom range: `lb:r<from>-<to>:msg:0` using compact day numbers.

Behaviour rules:

- Anyone in the chat can press buttons (shared board, like Combot). Optional setting: only the requester can press.
- A board older than 24 h still works; stale data is re-queried, never cached forever.
- Per-chat in-memory cache with ~10 s TTL to survive button-mashing.
- Telegram "message is not modified" errors are swallowed.

---

## 5. Architecture

```
            ┌──────────────┐   updates    ┌─────────────────────────┐
 Telegram ─▶│ aiogram      │─────────────▶│ routers                 │
            │ (polling →   │              │  tracker  (no replies)  │
            │  webhook)    │◀─────────────│  leaderboard / me / ... │
            └──────────────┘ rich msgs    └───────┬─────────────────┘
                                                  │
                          ┌───────────────────────┼────────────────────┐
                          ▼                       ▼                    ▼
                 ┌─────────────────┐    ┌──────────────────┐   ┌──────────────┐
                 │ Collector       │    │ Stats service    │   │ Renderer     │
                 │ in-memory buffer│    │ SQL queries,     │   │ rich blocks  │
                 │ flush every 5 s │    │ ranks, caching   │   │ + HTML fallb.│
                 └────────┬────────┘    └────────┬─────────┘   └──────────────┘
                          └──────────┬───────────┘
                                     ▼
                              PostgreSQL (asyncpg)
```

### 5.1 Repository layout

```
hubbub/
├─ pyproject.toml
├─ Dockerfile
├─ docker-compose.yml
├─ .env.example
├─ README.md
├─ PLAN.md
├─ migrations/
│  ├─ 001_init.sql
│  └─ 002_...sql
├─ src/hubbub/
│  ├─ __main__.py            # entrypoint: build bot, run polling/webhook
│  ├─ config.py              # pydantic-settings
│  ├─ db.py                  # asyncpg pool, migration runner
│  ├─ collector.py           # buffer + periodic flush
│  ├─ stats.py               # queries: top, me, hours, totals
│  ├─ periods.py             # period parsing, tz-aware ranges
│  ├─ callbacks.py           # callback_data encode/decode (CallbackData)
│  ├─ handlers/
│  │  ├─ tracker.py          # message → collector (no output)
│  │  ├─ leaderboard.py      # /top + button callbacks
│  │  ├─ me.py               # /me
│  │  ├─ privacy.py          # /optout /optin /forgetme /pause
│  │  ├─ settings.py         # /settings (admin)
│  │  └─ common.py           # /start /help, my_chat_member
│  ├─ render/
│  │  ├─ rich.py             # blocks builders (table, buttons, headings)
│  │  ├─ fallback.py         # HTML text renderer
│  │  └─ bars.py             # ▰▱ bars, sparklines ▁▂▃▅▇
│  └─ i18n/                  # en.json (ru.json later)
└─ tests/
   ├─ test_periods.py
   ├─ test_collector.py
   ├─ test_stats.py          # testcontainers / pg fixture
   └─ test_render.py
```

### 5.2 Dependencies (keep it short)

- `aiogram>=3.31`
- `asyncpg`
- `pydantic-settings`
- `tzdata` (zoneinfo)
- dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`

No ORM, no Redis, no Celery. Plain SQL files + asyncpg.

---

## 6. Data model

Store **hourly aggregates**, never individual messages. Any period and any time-of-day board is a `SUM` over this table.

```sql
-- migrations/001_init.sql
CREATE TABLE chats (
    chat_id     BIGINT PRIMARY KEY,
    title       TEXT,
    tz          TEXT        NOT NULL DEFAULT 'UTC',
    collecting  BOOLEAN     NOT NULL DEFAULT TRUE,   -- admin /pause
    only_requester BOOLEAN  NOT NULL DEFAULT FALSE,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    user_id     BIGINT PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE activity_hourly (
    chat_id     BIGINT      NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    user_id     BIGINT      NOT NULL,
    bucket      TIMESTAMPTZ NOT NULL,                -- UTC, truncated to hour
    msgs        INTEGER     NOT NULL DEFAULT 0,
    chars       INTEGER     NOT NULL DEFAULT 0,
    media       INTEGER     NOT NULL DEFAULT 0,
    replies     INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id, bucket)
);
CREATE INDEX activity_chat_bucket ON activity_hourly (chat_id, bucket);

CREATE TABLE optouts (
    chat_id     BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);
```

Flush (batched `executemany`):

```sql
INSERT INTO activity_hourly (chat_id, user_id, bucket, msgs, chars, media, replies)
VALUES ($1,$2,$3,$4,$5,$6,$7)
ON CONFLICT (chat_id, user_id, bucket) DO UPDATE SET
    msgs    = activity_hourly.msgs    + EXCLUDED.msgs,
    chars   = activity_hourly.chars   + EXCLUDED.chars,
    media   = activity_hourly.media   + EXCLUDED.media,
    replies = activity_hourly.replies + EXCLUDED.replies;
```

Leaderboard query (metric column is whitelisted, never interpolated from user input):

```sql
SELECT a.user_id, u.username, u.first_name,
       SUM(a.msgs) AS value,
       SUM(SUM(a.msgs)) OVER () AS total
FROM activity_hourly a
JOIN users u USING (user_id)
WHERE a.chat_id = $1 AND a.bucket >= $2 AND a.bucket < $3
GROUP BY a.user_id, u.username, u.first_name
ORDER BY value DESC
LIMIT 10 OFFSET $4;
```

Time-of-day boards: filter on `EXTRACT(HOUR FROM bucket AT TIME ZONE chats.tz)`.
Period boundaries ("today", "7d") are computed in the **chat's timezone** and converted to UTC.

Size estimate: one row per active user per active hour. A chat with 500 active users ≈ a few MB per month. Optional retention job (`DELETE … WHERE bucket < now() - interval '2 years'`) if it ever matters.

---

## 7. Collector (the hot path)

```
message ─▶ tracker handler ─▶ Collector.add(chat, user, ts, msgs=1, chars, media, replies)
                                   │  dict[(chat,user,hour)] → counters
                                   ▼
              every 5 s (or ≥ 500 keys) ─▶ swap buffer ─▶ executemany upsert
              on shutdown ─▶ final flush
```

Rules:

- Count only `group` / `supergroup`; ignore private chats and channels.
- Ignore: messages from bots, service messages, `sender_chat` (anonymous admin / linked channel), `is_automatic_forward`, edited messages.
- `chars` = `len(text or caption)`; `media` = 1 for any photo / video / voice / video note / sticker / animation / document.
- Never persist or log message text.
- Skip chats with `collecting = false` and users in `optouts` (opt-outs cached in memory, refreshed on change).
- Upsert user profile (`username`, `first_name`) at most once per N minutes per user.
- Worst case on crash: lose ≤ 5 s of counters. Acceptable.

Telegram setup: **disable privacy mode** in BotFather (or make the bot an admin), otherwise it won't see normal group messages. Allowed updates: `message`, `callback_query`, `my_chat_member`.

---

## 8. Commands

| Command | Who | Result |
|---|---|---|
| `/top` | anyone | leaderboard rich message (default: 7d, messages) |
| `/top today\|7d\|30d\|all` | anyone | same, preselected period |
| `/me` | anyone | personal card |
| `/hours` | anyone | time-of-day board *(v0.2)* |
| `/stats` | anyone | chat summary *(v0.2)* |
| `/optout` `/optin` | anyone | stop / resume counting me |
| `/forgetme` | anyone | confirm button → wipe my rows in this chat |
| `/settings` | admins | timezone, pause, requester-only |
| `/pause` `/resume` | admins | stop / resume collection for the chat |
| `/help` | anyone | short rich help |

Anti-flood: per-chat cooldown on `/top` (e.g. 10 s); callbacks are not limited but are cached.

---

## 9. Rendering layer

`render/rich.py` exposes pure functions, easy to unit-test:

```python
def leaderboard(rows, *, period, metric, page, pages, total, active, updated_at) -> InputRichMessage: ...
def me_card(profile) -> InputRichMessage: ...
def settings_panel(chat) -> InputRichMessage: ...
```

- Build with `blocks=[...]` (typed, no escaping bugs) rather than `markdown`/`html` strings.
- Display name: `@username` if present, else first name; **escape/neutralise** weird names (RTL marks, very long names → truncate to ~18 chars).
- Bars: `▰▱` ×8, sparklines `▁▂▃▄▅▆▇█` — pure text, works everywhere.
- `render/fallback.py` produces equivalent HTML text + classic `InlineKeyboardMarkup`; used when rich send/edit raises an API error or `RICH_ENABLED=false`.
- Sending in groups: `await message.answer_rich(rich_message=...)`; editing: `bot.edit_message_text(..., rich_message=...)` (check the exact aiogram kwarg names against the 3.31 docs).

---

## 10. Config (`.env`)

```
BOT_TOKEN=
DATABASE_URL=postgresql://hubbub:***@db:5432/hubbub
FLUSH_INTERVAL_SEC=5
FLUSH_MAX_KEYS=500
PAGE_SIZE=10
TOP_COOLDOWN_SEC=10
RICH_ENABLED=true
DEFAULT_TZ=UTC
LOG_LEVEL=INFO
# webhook mode (optional)
WEBHOOK_URL=
WEBHOOK_SECRET=
```

---

## 11. Deployment

`docker-compose.yml`: two services — `bot` and `db` (postgres:16-alpine) with a named volume. Long polling at first (no domain or TLS needed); switch to webhook behind your reverse proxy when you want zero idle polling.

- Migrations: run `migrations/*.sql` in order at startup (a `schema_migrations` table tracks applied files).
- Backups: nightly `pg_dump` via cron to a second location.
- Logs: structured to stdout; `docker logs` is enough.
- Health: a periodic log line with buffer size, flush time and rows/s.

---

## 12. Testing

- **Unit**: period math across DST and timezones, callback encode/decode, bars/sparklines, collector merge logic.
- **DB**: upsert correctness, top queries with ties (tie-break by `user_id` for stable order), pagination, opt-out and wipe.
- **Render snapshots**: `InputRichMessage.model_dump()` snapshots for the leaderboard with 0, 1, 10, 50 rows and weird names.
- **Manual**: real test supergroup with 3 accounts before every release.

---

## 13. Milestones

| # | Goal | Done when |
|---|---|---|
| 0 | **Rich Messages spike** | a throwaway script sends a table + button row to a test group and edits it in place |
| 1 | Skeleton + DB | bot starts, migrations apply, `/start` works |
| 2 | Collector | messages counted, buffer flushed, verified against manual counts |
| 3 | `/top` v1 | period + metric + pager buttons edit one message |
| 4 | `/me` + privacy | card, `/optout`, `/forgetme`, `/pause` |
| 5 | Polish + fallback | HTML fallback, cooldowns, error handling, README |
| 6 | **v0.1 release** | runs in 1–2 real chats for a week without babysitting |
| 7 | v0.2 | hour boards, date ranges, timezone, `/stats` |

---

## 14. Risks and open questions

- **Rich Messages are new** (June 2026) — expect client rendering differences; the fallback renderer is not optional.
- Library API for rich text types (`RichTextUnion`) must be checked in the docs while building the renderer.
- Large chats (> 10k msgs/hour): the in-memory buffer handles it, but verify flush latency.
- Name changes: users are keyed by `user_id`; username/first name refresh is best-effort.
- Telegram privacy / store policies: collect only counters, state this in `/help`, keep the wipe command working.

---

## Naming

Short, memorable, available-sounding English names (**BotFather availability not checked** — usernames must end in `bot`, e.g. `@hubbub_bot`).

| Name | Vibe | Tagline |
|---|---|---|
| **Hubbub** ★ | the noise of a busy crowd | *Who's making all the noise?* |
| **Noisefloor** ★ | techy, calm, a bit nerdy | *Hear who's loudest.* |
| **Yapboard** ★ | playful, meme-friendly | *Leaderboard for yappers.* |
| Tallybird | cute mascot (a bird counting chirps) | *Counts every chirp.* |
| Murmur | quiet, passive observer | *Listens. Never speaks.* |
| Loudest | blunt, one word | *Find the loudest one.* |
| Echo Ledger | elegant, ledger of chat echoes | *Every message, accounted for.* |
| Chatterlog | descriptive | *Your chat, in numbers.* |
| Rumor Mill | gossipy, fun | *Who talks the most.* |
| Peakhour | focused on activity peaks | *When your chat comes alive.* |

Top picks: **Hubbub** (best brand potential, easy to say in any language), **Noisefloor** (most distinctive), **Yapboard** (most viral).
