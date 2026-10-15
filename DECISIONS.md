# DECISIONS.md

1. **Indexes.**
   Created unique indexes on `employees.emp_code` and `attendance_logs.(emp_code, date)` to enforce identity uniqueness and race-safe punch-ins. Created compound indexes on `attendance_logs`: `(date: -1, emp_code: 1)` for index-backed cursor pagination, `(emp_code: 1, punch_in: -1)` for O(1) punch-out open-record lookups even with millions of historical rows, and `(date: 1, late_minutes: 1)` for the late leaderboard. On `employees`: `(department: 1, joined_on: 1)` to accelerate department filtering and headcount pruning. Considered and rejected an index on `status` alone due to low cardinality, which provides poor selectivity compared to composite date bounds.

2. **Punch-in race.**
   Both requests compute the attendance date concurrently and attempt insertion into `attendance_logs`. MongoDB's unique compound index on `(emp_code, date)` atomically commits the first insert and rejects the second with `DuplicateKeyError` (code 11000). The application intercepts this exception and returns HTTP 409 Conflict, ensuring exactly one 201 and one 409 without dirty state.

3. **Ties.**
   The leaderboard applies standard competition ranking (`$rank` in `$setWindowFields`) where tied employees share a rank and subsequent ranks are skipped (e.g. 1, 2, 2, 4). Because `limit` filters `rank <= limit` after ranking, all employees tied at or below the cutoff rank are returned. The response may contain more than `limit` rows, ordered secondary by `emp_code` ascending.

4. **Headcount.**
   The department summary pipeline roots its aggregation in `employees` matching `joined_on <= end_of_month`, `$lookup`s `attendance_logs`, and unwinds with `preserveNullAndEmptyArrays: True`. Employees with zero logs produce a row with null attendance fields. Headcount is computed as `$size: { $addToSet: "$emp_code" }`, ensuring every employee is counted.

5. **One thing you would change for 100x data.**
   At 10M+ records, calculating moving averages via cross-collection lookups and dynamic densification degrades throughput. I would shard `attendance_logs` on a hashed `(emp_code, date)` key and maintain a pre-aggregated daily rollup collection populated asynchronously via MongoDB Change Streams, allowing trend and summary analytics to query pre-computed daily totals in O(1) time.
