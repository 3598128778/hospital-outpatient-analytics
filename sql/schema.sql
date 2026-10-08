CREATE TABLE IF NOT EXISTS registrations (
 registration_id VARCHAR(40) PRIMARY KEY,
 business_date VARCHAR(10) NOT NULL,
 department VARCHAR(30) NOT NULL,
 period VARCHAR(10) NOT NULL,
 status VARCHAR(12) NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
 visit_id VARCHAR(40) PRIMARY KEY,
 registration_id VARCHAR(40) NOT NULL UNIQUE,
 status VARCHAR(12) NOT NULL,
 FOREIGN KEY (registration_id) REFERENCES registrations(registration_id)
);
CREATE TABLE IF NOT EXISTS charges (
 charge_id VARCHAR(40) PRIMARY KEY,
 registration_id VARCHAR(40) NOT NULL,
 kind VARCHAR(12) NOT NULL,
 amount_cents BIGINT NOT NULL,
 FOREIGN KEY (registration_id) REFERENCES registrations(registration_id)
);
