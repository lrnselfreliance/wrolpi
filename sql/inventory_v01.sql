CREATE TABLE inventory
(
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE item
(
    id              SERIAL PRIMARY KEY,
    inventory_id    INTEGER REFERENCES inventory (id) NOT NULL,
    brand           TEXT,
    name            TEXT,
    count           DECIMAL,
    item_size       DECIMAL,
    unit            TEXT,
    serving         INT,
    category        TEXT,
    subcategory     TEXT,
    expiration_date DATE,
    purchase_date   DATE,
    created_at      TIMESTAMP,
    deleted_at      TIMESTAMP
);

CREATE TABLE category
(
    id          SERIAL PRIMARY KEY,
    subcategory TEXT NOT NULL,
    category    TEXT NOT NULL,
    UNIQUE (subcategory, category)
);
