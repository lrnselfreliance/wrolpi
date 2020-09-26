-- Initial inventory schema.
-- depends: 

CREATE TABLE public.inventory
(
    id         integer NOT NULL,
    name       text    NOT NULL,
    viewed_at  timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamp without time zone
);

CREATE SEQUENCE public.inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.inventory_id_seq OWNED BY public.inventory.id;

CREATE TABLE public.item
(
    id              integer NOT NULL,
    inventory_id    integer,
    brand           text,
    name            text,
    count           numeric,
    item_size       numeric,
    unit            text,
    serving         integer,
    category        text,
    subcategory     text,
    expiration_date date,
    purchase_date   date,
    created_at      timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_at      timestamp without time zone
);

CREATE SEQUENCE public.item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.item_id_seq OWNED BY public.item.id;

ALTER TABLE ONLY public.inventory
    ALTER COLUMN id SET DEFAULT nextval('public.inventory_id_seq'::regclass);

ALTER TABLE ONLY public.item
    ALTER COLUMN id SET DEFAULT nextval('public.item_id_seq'::regclass);

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_name_key UNIQUE (name);

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.item
    ADD CONSTRAINT item_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.video
    ADD CONSTRAINT video_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.item
    ADD CONSTRAINT item_inventory_id_fkey FOREIGN KEY (inventory_id) REFERENCES public.inventory (id);

ALTER TABLE ONLY public.video
    ADD CONSTRAINT video_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channel (id) ON DELETE CASCADE;
