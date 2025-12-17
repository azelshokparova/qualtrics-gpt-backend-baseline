from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)

# Load your API key from Render environment settings
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.route("/qualtrics-response", methods=["POST"])
def qualtrics_response():
    user_text = request.form.get("prompt", "")

    # You can adjust system prompt as needed
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert mental health therapist responding to someone describing a personal experience. "
            )
        },
        {"role": "user", "content": user_text}
    ]

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )
        reply = completion.choices[0].message.content

    except Exception as e:
        reply = f"ERROR: {str(e)}"

    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)




