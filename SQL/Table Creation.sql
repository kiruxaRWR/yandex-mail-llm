-- ============================================================
-- Удаление старых версий таблиц (в порядке, обратном зависимостям)
-- ============================================================
DROP TABLE IF EXISTS public.events          CASCADE;
DROP TABLE IF EXISTS public.email_decisions CASCADE;
DROP TABLE IF EXISTS public.email_analysis  CASCADE;
DROP TABLE IF EXISTS public.emails          CASCADE;

-- ============================================================
-- Таблицы для хранения и анализа email-сообщений
-- PostgreSQL
-- ============================================================

-- Таблица emails
CREATE TABLE IF NOT EXISTS public.emails (
    id                  bigserial       NOT NULL,
    message_id          text            NOT NULL,
    folder              text            NOT NULL DEFAULT 'INBOX',
    sender              text,
    subject             text,
    received_at         timestamptz,
    raw_text            text,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    imap_uid            text,
    category            text,
    category_confidence numeric,
    needs_review        boolean         NOT NULL DEFAULT false,
    CONSTRAINT emails_pkey PRIMARY KEY (id),
    CONSTRAINT emails_message_id_key UNIQUE (message_id)
);

CREATE INDEX IF NOT EXISTS idx_emails_category    ON public.emails USING btree (category);
CREATE INDEX IF NOT EXISTS idx_emails_message_id  ON public.emails USING btree (message_id);
CREATE INDEX IF NOT EXISTS idx_emails_needs_review ON public.emails USING btree (needs_review) WHERE (needs_review = true);
CREATE INDEX IF NOT EXISTS idx_emails_received_at ON public.emails USING btree (received_at DESC);

-- Таблица email_analysis
CREATE TABLE IF NOT EXISTS public.email_analysis (
    id                bigserial   NOT NULL,
    email_id          bigint      NOT NULL,
    model             text        NOT NULL,
    analysis          jsonb       NOT NULL,
    tokens_prompt     integer,
    tokens_completion integer,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT email_analysis_pkey PRIMARY KEY (id),
    CONSTRAINT email_analysis_email_id_fkey
        FOREIGN KEY (email_id) REFERENCES public.emails(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_analysis_email_id ON public.email_analysis USING btree (email_id);

-- Таблица email_decisions
CREATE TABLE IF NOT EXISTS public.email_decisions (
    id                   bigserial   NOT NULL,
    email_id             bigint      NOT NULL,
    model                text        NOT NULL,
    category             text        NOT NULL,
    category_probability numeric     NOT NULL,
    raw_response         jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT email_decisions_pkey PRIMARY KEY (id),
    CONSTRAINT email_decisions_email_id_fkey
        FOREIGN KEY (email_id) REFERENCES public.emails(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_decisions_email_id ON public.email_decisions USING btree (email_id);

-- Таблица events
CREATE TABLE IF NOT EXISTS public.events (
    id                bigserial   NOT NULL,
    email_id          bigint      NOT NULL,
    type              text        NOT NULL,
    title             text,
    event_date        date,
    event_time        time,
    description       text,
    source_message_id text        NOT NULL,
    status            text        NOT NULL DEFAULT 'pending',
    created_at        timestamptz NOT NULL DEFAULT now(),
    links             jsonb,
    CONSTRAINT events_pkey PRIMARY KEY (id),
    CONSTRAINT events_email_id_fkey
        FOREIGN KEY (email_id) REFERENCES public.emails(id) ON DELETE CASCADE,
    CONSTRAINT events_unique_event
        UNIQUE (source_message_id, type, title, event_date, event_time)
);

CREATE INDEX IF NOT EXISTS idx_events_event_date ON public.events USING btree (event_date);
CREATE INDEX IF NOT EXISTS idx_events_status     ON public.events USING btree (status);