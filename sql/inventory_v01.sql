CREATE TABLE inventory
(
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    viewed_at  TIMESTAMP,
    created_at TIMESTAMP DEFAULT current_timestamp,
    deleted_at TIMESTAMP
);

CREATE TABLE item
(
    id              SERIAL PRIMARY KEY,
    inventory_id    INTEGER REFERENCES inventory (id),
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
    created_at      TIMESTAMP DEFAULT current_timestamp,
    deleted_at      TIMESTAMP
);
