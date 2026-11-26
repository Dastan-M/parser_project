CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rss_url VARCHAR(2048) NULL,
    use_browser BOOLEAN NOT NULL DEFAULT FALSE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO sources (name, url, domain, enabled, rss_url, use_browser) VALUES
('NUR.KZ', 'https://nur.kz', 'nur.kz', TRUE, NULL, TRUE),
('Zakon.KZ', 'https://zakon.kz', 'zakon.kz', TRUE, NULL, FALSE),
('KazTag', 'https://kaztag.kz', 'kaztag.kz', TRUE, 'https://kaztag.kz/upload/export/yandex-news.xml', FALSE),
('Time.KZ', 'https://time.kz', 'time.kz', TRUE, 'https://time.kz/rss', FALSE),
('Tengrinews', 'https://tengrinews.kz', 'tengrinews.kz', TRUE, 'http://tengrinews.kz/news.rss', FALSE),
('Inform.KZ', 'https://inform.kz', 'inform.kz', TRUE, NULL, TRUE),
('Orda.KZ', 'https://orda.kz', 'orda.kz', FALSE, NULL, FALSE),
('Total.KZ', 'https://total.kz', 'total.kz', FALSE, NULL, FALSE);