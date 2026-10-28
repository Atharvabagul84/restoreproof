CREATE SCHEMA app;
CREATE TABLE app.teams (id integer PRIMARY KEY, name text NOT NULL);
CREATE TABLE app.features (
    id integer PRIMARY KEY,
    team_id integer NOT NULL REFERENCES app.teams(id),
    title text NOT NULL,
    revision integer NOT NULL CHECK (revision > 0)
);
CREATE TABLE app.snapshots (
    feature_id integer NOT NULL REFERENCES app.features(id),
    revision integer NOT NULL,
    body text NOT NULL,
    PRIMARY KEY (feature_id, revision)
);
CREATE TABLE app.checkpoints (id integer PRIMARY KEY, committed_at timestamptz NOT NULL);
INSERT INTO app.teams VALUES (1, 'Flight systems'), (2, 'Ground operations');
INSERT INTO app.features VALUES (101, 1, 'Telemetry replay', 2), (102, 2, 'Release checklist', 1);
INSERT INTO app.snapshots VALUES (101, 1, 'First revision'), (101, 2, 'Durable replay'), (102, 1, 'Verified release');
INSERT INTO app.checkpoints VALUES (1, '2026-01-01T00:00:00Z');
