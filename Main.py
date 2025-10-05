"""
test.py — Simple Supabase Database Connection Tester for MeetEase
------------------------------------------------------------------
This script verifies your Supabase PostgreSQL connection and environment setup
before launching your full Streamlit app.

Usage:
    python test.py
"""

from dotenv import load_dotenv
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# ---------------- Load Environment Variables ----------------
print("📦 Loading environment variables from .env...")
load_dotenv()

SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_PORT = os.getenv("SUPABASE_PORT", "5432")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD")
SUPABASE_DATABASE = os.getenv("SUPABASE_DATABASE", "postgres")

# Debug-print to confirm what’s being loaded
print("\n🔍 Environment Configuration:")
print(f"  SUPABASE_HOST      = {SUPABASE_HOST}")
print(f"  SUPABASE_PORT      = {SUPABASE_PORT}")
print(f"  SUPABASE_USER      = {SUPABASE_USER}")
print(f"  SUPABASE_DATABASE  = {SUPABASE_DATABASE}")
print("  SUPABASE_PASSWORD  = (hidden)\n")


# ---------------- Test Database Connection ----------------
def test_connection():
    print("🧠 Attempting PostgreSQL connection via psycopg2...\n")
    try:
        conn = psycopg2.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            dbname=SUPABASE_DATABASE,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD.strip('"').strip("'"),
            sslmode="require",
            connect_timeout=10,
            cursor_factory=RealDictCursor
        )
        print("✅ SUCCESS: Connected to Supabase PostgreSQL!\n")

        # Optional: quick sanity query
        cur = conn.cursor()
        cur.execute("SELECT current_database() AS db, current_user AS user, version();")
        row = cur.fetchone()
        print("📊 Connection Info:")
        print(f"   Database: {row['db']}")
        print(f"   User: {row['user']}")
        print(f"   Version: {row['version'][:80]}...\n")

        # Optional: check if 'meetings' table exists
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        tables = [r["table_name"] for r in cur.fetchall()]
        print("📁 Tables found in database:")
        for t in tables:
            print(f"   - {t}")
        print("\n✅ All good! You can now run your Streamlit app safely.")

        conn.close()

    except psycopg2.OperationalError as e:
        print("❌ CONNECTION ERROR:")
        print(str(e))
        print("\n💡 Possible causes:")
        print("  1️⃣ Wrong SUPABASE_PASSWORD or host")
        print("  2️⃣ Streamlit Cloud IPv6 issue → try Pooler Host instead")
        print("  3️⃣ Port closed (use 5432, not 6543)")
        print("  4️⃣ Forgot sslmode='require'")
        print("\n👉 To fix: check .env file and verify your credentials in Supabase → Settings → Database.")
    except Exception as e:
        print("⚠️ Unexpected error:", e)


if __name__ == "__main__":
    test_connection()
