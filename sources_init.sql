CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rss_url VARCHAR(2048) NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO sources (name, url, domain, enabled, rss_url) VALUES
('NUR.KZ', 'https://nur.kz', 'nur.kz', TRUE, NULL),
('Zakon.KZ', 'https://zakon.kz', 'zakon.kz', TRUE, NULL),
('KazTag', 'https://kaztag.kz', 'kaztag.kz', TRUE, 'https://kaztag.kz/upload/export/yandex-news.xml'),
('Time.KZ', 'https://time.kz', 'time.kz', TRUE, 'https://time.kz/rss');