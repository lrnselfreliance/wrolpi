-- Initial video schema.
-- depends: 

CREATE TABLE public.channel
(
    id                   integer NOT NULL,
    name                 text,
    link                 text,
    idempotency          text,
    url                  text,
    match_regex          text,
    directory            text,
    info_json            json,
    info_date            date,
    skip_download_videos text[],
    generate_posters     boolean DEFAULT true,
    calculate_duration   boolean DEFAULT true,
    download_frequency   integer,
    next_download        date
);

CREATE SEQUENCE public.channel_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.channel_id_seq OWNED BY public.channel.id;

CREATE TABLE public.video
(
    id               integer NOT NULL,
    description_path text,
    ext              text,
    poster_path      text,
    source_id        text,
    title            text,
    video_path       text,
    caption_path     text,
    idempotency      text,
    info_json_path   text,
    channel_id       integer,
    caption          text,
    textsearch       tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig,
                                                               ((COALESCE(title, ''::text) || ' '::text) ||
                                                                COALESCE(caption, ''::text)))) STORED,
    upload_date      timestamp without time zone,
    duration         integer,
    favorite         timestamp without time zone,
    size             bigint,
    viewed           timestamp without time zone,
    validated_poster boolean DEFAULT false
);

CREATE SEQUENCE public.video_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.video_id_seq OWNED BY public.video.id;

ALTER TABLE ONLY public.channel
    ALTER COLUMN id SET DEFAULT nextval('public.channel_id_seq'::regclass);

ALTER TABLE ONLY public.video
    ALTER COLUMN id SET DEFAULT nextval('public.video_id_seq'::regclass);

ALTER TABLE ONLY public.channel
    ADD CONSTRAINT channel_pkey PRIMARY KEY (id);

CREATE INDEX textsearch_idx ON public.video USING gin (textsearch);

CREATE INDEX video_duration_idx ON public.video USING btree (duration);

CREATE INDEX video_favorite_idx ON public.video USING btree (favorite);

CREATE INDEX video_size_idx ON public.video USING btree (size);

CREATE INDEX video_upload_date_idx ON public.video USING btree (upload_date);

CREATE INDEX video_viewed_idx ON public.video USING btree (viewed);
