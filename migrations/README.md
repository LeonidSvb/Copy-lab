# Migrations

SQL migration files applied in order by db.py on startup.

Naming: `{number}_{description}.sql`
Example: `001_initial_schema.sql`, `002_add_baseline_variants.sql`

db.py tracks which migrations have been applied in the `schema_migrations` table.
Never edit an existing migration — always add a new one.
