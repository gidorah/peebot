from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("telemetry_storage", "0001_initial_v2"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- 1. Drop existing Primary Key (on id)
            -- Note: Standard Django naming convention is 'table_name_pkey'
            ALTER TABLE telemetry_storage_telemetryreading DROP CONSTRAINT telemetry_storage_telemetryreading_pkey;

            -- 2. Create Composite Primary Key (id, timestamp)
            -- Mandatory for Hypertables with Unique/PK constraints
            ALTER TABLE telemetry_storage_telemetryreading ADD PRIMARY KEY (id, timestamp);

            -- 3. Convert to Hypertable with 1-day chunks
            SELECT create_hypertable(
                'telemetry_storage_telemetryreading',
                'timestamp',
                chunk_time_interval => INTERVAL '1 day',
                migrate_data => true,
                if_not_exists => true
            );

            -- 4. Configure Compression
            -- Segment by channel_id to optimize queries for specific sensors
            ALTER TABLE telemetry_storage_telemetryreading SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'channel_id',
                timescaledb.compress_orderby = 'timestamp DESC'
            );

            -- 5. Add Compression Policy (Compress after 7 days)
            SELECT add_compression_policy(
                'telemetry_storage_telemetryreading',
                INTERVAL '7 days',
                if_not_exists => true
            );

            -- 6. Add Retention Policy (Drop data older than 30 days)
            SELECT add_retention_policy(
                'telemetry_storage_telemetryreading',
                INTERVAL '30 days',
                if_not_exists => true
            );
            """,
            reverse_sql="""
            SELECT remove_retention_policy('telemetry_storage_telemetryreading', if_exists => true);
            SELECT remove_compression_policy('telemetry_storage_telemetryreading', if_exists => true);
            -- Reversing Primary Key changes is skipped in dev rollback to avoid data loss risks.
            """,
        ),
    ]
