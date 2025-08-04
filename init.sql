CREATE TABLE favorites (
    id SERIAL PRIMARY KEY,
    type VARCHAR(10),
    title TEXT,
    url TEXT,
    image TEXT
);

CREATE TABLE search_history (
    id SERIAL PRIMARY KEY,
    query TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);
