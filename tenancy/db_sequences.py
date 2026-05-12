from django.db import connection


def reset_schema_sequences(cursor, schema_name, table_names=None):
    """Set PostgreSQL sequences in a schema to the current max table value."""
    params = [schema_name]
    table_filter = ""

    if table_names is not None:
        table_names = sorted(set(table_names))
        if not table_names:
            return []
        placeholders = ", ".join(["%s"] * len(table_names))
        table_filter = f"AND t.relname IN ({placeholders})"
        params.extend(table_names)

    cursor.execute(
        f"""
        SELECT t.relname AS table_name,
               a.attname AS column_name,
               s.relname AS sequence_name
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S'
          AND n.nspname = %s
          {table_filter}
        ORDER BY t.relname, a.attname
        """,
        params,
    )

    reset_sequences = []
    quoted_schema = connection.ops.quote_name(schema_name)

    for table_name, column_name, sequence_name in cursor.fetchall():
        quoted_table = connection.ops.quote_name(table_name)
        quoted_column = connection.ops.quote_name(column_name)
        quoted_sequence = (
            f"{quoted_schema}.{connection.ops.quote_name(sequence_name)}"
        )

        cursor.execute(
            f"""
            SELECT setval(
                %s::regclass,
                COALESCE(
                    (SELECT MAX({quoted_column}) FROM {quoted_schema}.{quoted_table}),
                    1
                ),
                COALESCE(
                    (SELECT MAX({quoted_column}) FROM {quoted_schema}.{quoted_table}),
                    0
                ) > 0
            )
            """,
            [quoted_sequence],
        )
        reset_sequences.append((table_name, column_name, cursor.fetchone()[0]))

    return reset_sequences
