CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO sources (name, url, domain, enabled) VALUES
('NUR.KZ', 'https://nur.kz', 'nur.kz', TRUE),
('Zakon.KZ', 'https://zakon.kz', 'zakon.kz', TRUE),
('KazTag', 'https://kaztag.kz', 'kaztag.kz', TRUE);