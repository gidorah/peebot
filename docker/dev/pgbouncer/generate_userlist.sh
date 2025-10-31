#!/usr/bin/env bash
# ==============================================================================
# PgBouncer Userlist Generator
# ==============================================================================
# Generates SCRAM-SHA-256 password hashes for PgBouncer's userlist.txt
#
# Usage:
#   ./generate_userlist.sh <username> <password>
#
# Example:
#   ./generate_userlist.sh pgbouncer_auth my_secure_password
#
# Output format (for userlist.txt):
#   "username" "SCRAM-SHA-256$4096:salt$hash$hash"
#
# Requirements:
#   - PostgreSQL client (psql) with access to a running PostgreSQL instance
#   OR
#   - Python 3 with passlib library (pip install passlib)
# ==============================================================================

set -e  # Exit on error

# ------------------------------------------------------------------------------
# Argument validation
# ------------------------------------------------------------------------------
if [ "$#" -ne 2 ]; then
    echo "ERROR: Invalid number of arguments"
    echo ""
    echo "Usage: $0 <username> <password>"
    echo ""
    echo "Example:"
    echo "  $0 pgbouncer_auth my_secure_password"
    echo ""
    echo "This script generates a SCRAM-SHA-256 password hash compatible with"
    echo "PgBouncer's userlist.txt file format."
    exit 1
fi

USERNAME="$1"
PASSWORD="$2"

# ------------------------------------------------------------------------------
# Method 1: Use PostgreSQL to generate SCRAM hash (preferred)
# ------------------------------------------------------------------------------
generate_with_postgres() {
    echo "Using PostgreSQL to generate SCRAM-SHA-256 hash..." >&2

    # Check if psql is available
    if ! command -v psql &> /dev/null; then
        return 1
    fi

    # Try to connect to local PostgreSQL (adjust connection string as needed)
    # This works if you have a local PostgreSQL instance running
    local pg_conn="${DATABASE_URL:-postgresql://peebot_user:password@localhost:5432/peebot}"

    # Generate SCRAM hash using PostgreSQL
    local scram_hash
    scram_hash=$(psql "$pg_conn" -t -A -c "SELECT passwd FROM pg_shadow WHERE usename = current_user LIMIT 1;" 2>/dev/null)

    if [ -z "$scram_hash" ]; then
        # Fallback: Create temporary role to get hash format
        scram_hash=$(psql "$pg_conn" -t -A -c "
            DO \$\$
            DECLARE
                temp_hash text;
            BEGIN
                -- Create temporary role with the password
                EXECUTE format('CREATE ROLE temp_scram_user_%s WITH PASSWORD %L',
                              floor(random() * 1000000)::int,
                              '$PASSWORD');

                -- Get the SCRAM hash
                SELECT passwd INTO temp_hash
                FROM pg_shadow
                WHERE usename LIKE 'temp_scram_user_%';

                -- Drop the temporary role
                EXECUTE format('DROP ROLE temp_scram_user_%s',
                              floor(random() * 1000000)::int);

                RAISE NOTICE '%', temp_hash;
            END \$\$;
        " 2>&1 | grep 'SCRAM-SHA-256' || true)
    fi

    if [ -n "$scram_hash" ] && [[ "$scram_hash" == SCRAM-SHA-256* ]]; then
        echo "\"$USERNAME\" \"$scram_hash\""
        return 0
    fi

    return 1
}

# ------------------------------------------------------------------------------
# Method 2: Use Python with passlib (fallback)
# ------------------------------------------------------------------------------
generate_with_python() {
    echo "Using Python to generate SCRAM-SHA-256 hash..." >&2

    # Check if python3 is available
    if ! command -v python3 &> /dev/null; then
        return 1
    fi

    # Generate hash using Python
    python3 - <<EOF
import sys
try:
    from passlib.hash import scram

    # Generate SCRAM-SHA-256 hash (PostgreSQL format)
    # Note: passlib's scram.using() creates RFC 5802 compliant hashes
    # but PostgreSQL uses a slightly different format

    # For now, we'll use a simpler approach with hashlib
    import hashlib
    import base64
    import os

    # Generate salt
    salt = base64.b64encode(os.urandom(16)).decode('ascii')

    # SCRAM parameters
    iterations = 4096
    password = "$PASSWORD".encode('utf-8')

    # Compute salted password
    salted_password = hashlib.pbkdf2_hmac(
        'sha256',
        password,
        base64.b64decode(salt),
        iterations
    )

    # Compute ClientKey and ServerKey
    client_key = hashlib.new('sha256', salted_password + b"Client Key").digest()
    stored_key = hashlib.new('sha256', client_key).digest()
    server_key = hashlib.new('sha256', salted_password + b"Server Key").digest()

    # Format as PostgreSQL SCRAM-SHA-256 format
    scram_hash = f"SCRAM-SHA-256\${iterations}:{salt}\${base64.b64encode(stored_key).decode('ascii')}\${base64.b64encode(server_key).decode('ascii')}"

    print(f'"$USERNAME" "{scram_hash}"')

except ImportError:
    print("ERROR: Python passlib library not installed", file=sys.stderr)
    print("Install with: pip install passlib", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to generate hash: {e}", file=sys.stderr)
    sys.exit(1)
EOF

    return $?
}

# ------------------------------------------------------------------------------
# Method 3: Use Docker PostgreSQL container (most reliable for this project)
# ------------------------------------------------------------------------------
generate_with_docker() {
    echo "Using Docker PostgreSQL to generate SCRAM-SHA-256 hash..." >&2

    # Check if docker is available
    if ! command -v docker &> /dev/null; then
        return 1
    fi

    # Check if TimescaleDB container is running
    if ! docker ps --format '{{.Names}}' | grep -q 'peebot_timescaledb_dev'; then
        echo "WARNING: peebot_timescaledb_dev container not running" >&2
        return 1
    fi

    # Use the running TimescaleDB container to generate hash
    local scram_hash
    scram_hash=$(docker exec peebot_timescaledb_dev psql -U peebot_user -d peebot -t -A -c "
        DO \$\$
        DECLARE
            temp_role_name text;
            temp_hash text;
        BEGIN
            temp_role_name := 'temp_scram_' || floor(random() * 1000000)::text;

            EXECUTE format('CREATE ROLE %I WITH PASSWORD %L', temp_role_name, '$PASSWORD');

            SELECT passwd INTO temp_hash FROM pg_shadow WHERE usename = temp_role_name;

            EXECUTE format('DROP ROLE %I', temp_role_name);

            RAISE NOTICE '%', temp_hash;
        END \$\$;
    " 2>&1 | grep 'SCRAM-SHA-256' | sed 's/NOTICE:  //')

    if [ -n "$scram_hash" ] && [[ "$scram_hash" == SCRAM-SHA-256* ]]; then
        echo "\"$USERNAME\" \"$scram_hash\""
        return 0
    fi

    return 1
}

# ------------------------------------------------------------------------------
# Main execution - try methods in order
# ------------------------------------------------------------------------------
echo "Generating SCRAM-SHA-256 hash for user: $USERNAME" >&2
echo "" >&2

# Try Docker method first (most reliable for this project)
if generate_with_docker; then
    echo "" >&2
    echo "✓ Hash generated successfully!" >&2
    echo "" >&2
    echo "Add this line to docker/dev/pgbouncer/userlist.txt:" >&2
    exit 0
fi

# Try PostgreSQL method
if generate_with_postgres; then
    echo "" >&2
    echo "✓ Hash generated successfully!" >&2
    echo "" >&2
    echo "Add this line to docker/dev/pgbouncer/userlist.txt:" >&2
    exit 0
fi

# Try Python method
if generate_with_python; then
    echo "" >&2
    echo "✓ Hash generated successfully!" >&2
    echo "" >&2
    echo "Add this line to docker/dev/pgbouncer/userlist.txt:" >&2
    exit 0
fi

# ------------------------------------------------------------------------------
# All methods failed
# ------------------------------------------------------------------------------
echo "" >&2
echo "ERROR: Failed to generate SCRAM-SHA-256 hash" >&2
echo "" >&2
echo "Attempted methods:" >&2
echo "  1. Docker PostgreSQL container (peebot_timescaledb_dev)" >&2
echo "  2. Local PostgreSQL via psql" >&2
echo "  3. Python with passlib library" >&2
echo "" >&2
echo "Solutions:" >&2
echo "  - Start the development containers: just dev-up" >&2
echo "  - Or install PostgreSQL client tools: brew install postgresql" >&2
echo "  - Or install Python passlib: pip install passlib" >&2
echo "" >&2
exit 1
