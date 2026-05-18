# Supabase Setup

## Step 1: Create Supabase project

1. Go to supabase.com → New project
2. Name: `carecircle`
3. Password: pick a strong DB password, save it
4. Region: South Asia (Mumbai)
5. Wait ~2 minutes for project to provision

## Step 2: Get your API keys

Dashboard → Settings → API:
- Copy **Project URL** → `SUPABASE_URL` in `.env`
- Copy **service_role** key (NOT anon key) → `SUPABASE_SERVICE_KEY` in `.env`

## Step 3: Get OpenRouter key

Go to openrouter.ai → Keys → Create key → copy it → `OPENROUTER_API_KEY` in `.env`

## Step 4: Create `.env` file

Copy `.env.example` to `.env` and fill in the three values:

```
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJ...
OPENROUTER_API_KEY=sk-or-v1-...
```

## Step 5: Run the database schema

Dashboard → SQL Editor → New query → paste the entire contents of `db/schema.sql` → Run.

Expected: 17 tables created with no errors.

## Step 6: Create Storage bucket

Dashboard → Storage → New bucket:
- Name: `documents`
- Public: OFF (private)

## Step 7: Install dependencies and verify

```bash
cd "New CareCircle project"
pip install -r requirements.txt
python3 -c "
from db.client import get_db
db = get_db()
result = db.table('patients').select('id').limit(1).execute()
print('DB connection: OK')
"
```

## Step 8: Run the full test suite

```bash
pytest tests/ -v -s 2>&1 | tee test_results.txt
```

Expected: All tests pass. Terminal shows OCR text, LLM JSON responses, flags, drug safety checks, and patient summary.

## Step 9: Start the server

```bash
uvicorn main:app --reload --port 8001
```

Then open `test_ui/index.html` in your browser to manually test the full onboarding flow.
