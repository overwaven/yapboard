-- Aggregated word frequencies.
-- Only normalized word counts are stored: no message text, no word order and
-- no link to individual messages. `day` is the chat-local calendar day.
-- `stem` groups inflected forms (кот/кота/коту); `word` is the surface form
-- chosen for display.

CREATE TABLE IF NOT EXISTS word_counts (
    chat_id BIGINT  NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    user_id BIGINT  NOT NULL,
    day     DATE    NOT NULL,
    stem    TEXT    NOT NULL,
    word    TEXT    NOT NULL,
    n       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id, day, stem, word)
);

CREATE INDEX IF NOT EXISTS word_counts_chat_day
    ON word_counts (chat_id, day);
