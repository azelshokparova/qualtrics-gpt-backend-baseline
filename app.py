# app.py
import os
import hashlib

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import psycopg

app = Flask(__name__)
CORS(app)

# OpenAI client (expects OPENAI_API_KEY in Render env vars)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Postgres (expects DATABASE_URL in Render env vars)
DATABASE_URL = os.environ.get("DATABASE_URL")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def init_db():
    """Create table + indexes if they don't exist (safe to run on every start)."""
    if not DATABASE_URL:
        print("DATABASE_URL not set; skipping DB init")
        return

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS gpt_logs (
              id BIGSERIAL PRIMARY KEY,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              variant TEXT NOT NULL,
              user_text TEXT NOT NULL,
              user_text_sha256 TEXT NOT NULL,
              gpt_reply TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_gpt_logs_variant ON gpt_logs(variant);
            CREATE INDEX IF NOT EXISTS idx_gpt_logs_created_at ON gpt_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_gpt_logs_sha ON gpt_logs(user_text_sha256);
            """)
        conn.commit()

    print("DB init complete")
    
init_db()

def insert_log(variant: str, user_text: str, gpt_reply: str):
    """Insert one row. Failures shouldn't break the survey."""
    if not DATABASE_URL:
        return

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gpt_logs (variant, user_text, user_text_sha256, gpt_reply)
                VALUES (%s, %s, %s, %s)
                """,
                (variant, user_text, sha256(user_text), gpt_reply),
            )
        conn.commit()


@app.get("/health")
def health():
    return "ok", 200
    
@app.route("/qualtrics-response", methods=["POST"])
def qualtrics_response():
    payload = request.get_json(silent=True) or {}

    user_text = (payload.get("user_text") or payload.get("prompt") or "").strip()
    variant = (payload.get("variant") or "unknown").strip()

    # Return early if empty input (avoids storing junk)
    if not user_text:
        return jsonify({"reply": ""})

    system_prompt = (
        "You are an expert therapist whose primary goal is to provide effective guidance."
        "The therapeutic alliance (the relationship between a therapist and client) is important to therapy."
        "Your responses should be helpful and solution-oriented, but you do not need to focus on expressing emotional attunement or compassionate understanding beyond what is necessary for clarity and professionalism."
        "Therapy happens in a variety of locations: inpatient, outpatient, and the client's home."
        "It can involve multiple modalities including audio, video, text, and in-person, and can include the use of physical objects (e.g. to limit lethal means or for exposure)."
        "Outside of a conversation, a therapist might help a client access housing and employment."
        "They might prescribe  medication or assign homework. When necessary, a therapist may have to hospitalize a client."
        "Good therapy is client centered (e.g. involves shared decision making)."
        "Therapists themselves exhibit qualities such as offering hope, being trustworthy, treating clients equally, and showing interest."
        "They adhere to professional norms by communicating risks and benefits to a client, getting  informed consent, and keeping client data private."
        "Therapists are competent using methods such as case management, causal understanding (e.g. of a treatment algorithm,  by analyzing a client's false beliefs), and time management (e.g. pacing of a session)."
        "Therapeutic treatment is potentially harmful if applied wrong (e.g. with misdiagnosis, by colluding with delusions)."
        "There are a number of things a therapist should not do, such as: stigmatize a client, collude with delusions,  enable suicidal ideation, reinforce hallucinations, or enable mania. In many cases, a therapist should redirect a  client (e.g. appropriately challenge their thinking)."
        "Do not ask the user any follow-up questions. This is a one-shot interaction. Provide a complete response without requesting additional information or clarification."
        "Keep the response concise (approximately two short paragraphs) and ensure it ends with a complete sentence; if needed, stop early rather than mid-thought."
    )

    try:
        if not client.api_key:
            raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

        response = client.responses.create(
            model="gpt-5.2",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )

        reply = response.output_text or ""

    except Exception as e:
        reply = f"ERROR: {str(e)}"

    # Save to Postgres (do not break UX if DB insert fails)
    try:
        insert_log(variant, user_text, reply)
    except Exception as e:
        # Log for debugging; still return reply to Qualtrics
        print("DB insert failed:", str(e))

    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)














