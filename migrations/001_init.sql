-- Yapboard initial schema.
-- Stores hourly aggregates only; individual message text is never persisted.

CREATE TABLE IF NOT EXISTS chats (
    chat_id        BIGINT PRIMARY KEY,
    title          TEXT,
    tz             TEXT        NOT NULL DEFAULT 'UTC',
    collecting     BOOLEAN     NOT NULL DEFAULT TRUE,   -- admin /pause
    only_requester BOOLEAN     NOT NULL DEFAULT FALSE,
    added_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    user_id    BIGINT PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS activity_hourly (
    chat_id BIGINT      NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    user_id BIGINT      NOT NULL,
    bucket  TIMESTAMPTZ NOT NULL,                       -- UTC, truncated to hour
    msgs    INTEGER     NOT NULL DEFAULT 0,
    chars   INTEGER     NOT NULL DEFAULT 0,
    media   INTEGER     NOT NULL DEFAULT 0,
    replies INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id, bucket)
);

CREATE INDEX IF NOT EXISTS activity_chat_bucket ON activity_hourly (chat_id, bucket);
CREATE INDEX IF NOT EXISTS activity_chat_user_bucket
    ON activity_hourly (chat_id, user_id, bucket);

CREATE TABLE IF NOT EXISTS optouts (
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);
