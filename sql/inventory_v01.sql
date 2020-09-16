CREATE TABLE item
(
    id              SERIAL PRIMARY KEY,
    brand           TEXT,
    name            TEXT,
    count           DECIMAL,
    item_size       DECIMAL,
    unit            TEXT,
    serving         INT,
    category        TEXT,
    subcategory     TEXT,
    expiration_date DATE,
    purchase_date   DATE
);

CREATE TABLE category
(
    id          SERIAL PRIMARY KEY,
    subcategory TEXT NOT NULL,
    category    TEXT NOT NULL,
    UNIQUE (subcategory, category)
);
