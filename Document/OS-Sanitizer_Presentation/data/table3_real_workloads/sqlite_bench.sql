-- omnetpp/strcpy-like: many small string allocations/copies inside SQLite.
PRAGMA journal_mode = OFF;
PRAGMA synchronous = OFF;
CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT, grp INTEGER, payload TEXT);
WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 4000000)
INSERT INTO t(name, grp, payload)
SELECT printf('name-%08d', x), x % 1000, printf('%s-%s-%d', hex(x), upper(printf('p%d', x * 7)), x % 97) FROM c;
CREATE INDEX t_name ON t(name);
CREATE INDEX t_grp ON t(grp);
SELECT grp, count(*), max(length(payload)) FROM t GROUP BY grp ORDER BY 2 DESC LIMIT 3;
SELECT count(*) FROM t WHERE name LIKE 'name-0005%' OR payload LIKE '%-P7%';
SELECT count(*) FROM (SELECT substr(payload, 1, 6) || name AS k FROM t ORDER BY k);
