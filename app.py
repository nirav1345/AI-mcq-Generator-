# app.py (UPDATED: JSON-first MCQ generation with robust parsing & fallbacks)
from dotenv import load_dotenv
import os
import json
import re
import time
from flask import Flask, render_template, request, send_file
import pdfplumber
import docx
from werkzeug.utils import secure_filename
from fpdf import FPDF
import requests

load_dotenv()  # load env vars from .env

API_KEY = os.getenv("API_KEY")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULTS_FOLDER'] = 'results/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt', 'docx'}
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload (optional)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            text = ''.join([page.extract_text() or "" for page in pdf.pages])
        return text.strip()
    elif ext == 'docx':
        doc = docx.Document(file_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
        return text.strip()
    elif ext == 'txt':
        with open(file_path, 'r', encoding="utf-8") as file:
            return file.read().strip()
    return None


def extract_json_substring(s):
    """
    Find the first JSON array or object in string s and return it.
    This helps when model returns markdown or commentary around the JSON.
    """
    # Try to find a top-level array first (MCQs are an array)
    arr_match = re.search(r'(\[.*\])', s, flags=re.DOTALL)
    if arr_match:
        return arr_match.group(1)
    # Otherwise try to find an object (fallback)
    obj_match = re.search(r'(\{.*\})', s, flags=re.DOTALL)
    if obj_match:
        return obj_match.group(1)
    return None


def call_perplexity_json(prompt, timeout=20):
    """
    Call the Perplexity-like API and return text output (the assistant's content).
    This function only handles the HTTP call and returns raw text.
    """
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "sonar-reasoning-pro",
        "messages": [
            {"role": "system", "content": "You are an MCQ generator that MUST return only valid JSON (no extra commentary)."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Defensive: ensure expected structure
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if content is None:
            # some APIs return different shapes; try other access patterns
            # fallback: return raw text
            return resp.text
        return content.strip()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API request failed: {e}")
    except ValueError:
        # resp.json() failed
        return resp.text


def Question_mcqs_generator(input_text, num_questions, max_retries=1):
    """
    Returns a Python list of MCQs (each MCQ is dict with keys: question, options (dict A-D), correct)
    On error, raises RuntimeError with a descriptive message.
    """
    # Build prompt requesting strict JSON
    prompt = f"""
Generate exactly {num_questions} multiple-choice questions (MCQs) based on the text provided below.

**REQUIREMENTS (must follow exactly):**
- Output only valid JSON (no surrounding text, no backticks, no commentary).
- The top-level JSON MUST be an array of objects.
- Each object must have:
  - "question": string
  - "options": {"{"}"A":"string","B":"string","C":"string","D":"string"{"}"}  (all four keys present)
  - "correct": one of "A","B","C","D"
- Example output format:
[
  {{
    "question": "Question text?",
    "options": {{"A":"opt A","B":"opt B","C":"opt C","D":"opt D"}},
    "correct": "B"
  }},
  ...
]

Text to use for question generation:
\"\"\"{input_text}
\"\"\"
    """.strip()

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            raw = call_perplexity_json(prompt)
            print("\n=== RAW MCQ TEXT FROM API ===\n")
            print(raw)
            print("\n=== END RAW MCQ TEXT ===\n")

            # Try to parse directly first
            try:
                mcqs = json.loads(raw)
                # validate structure
                if not isinstance(mcqs, list):
                    raise ValueError("Top-level JSON is not a list.")
                validated = _validate_mcq_list(mcqs)
                return validated
            except json.JSONDecodeError:
                # Attempt to extract JSON substring and parse
                candidate = extract_json_substring(raw)
                if candidate:
                    try:
                        mcqs = json.loads(candidate)
                        validated = _validate_mcq_list(mcqs)
                        return validated
                    except Exception as e:
                        last_error = f"JSON extraction/parse failed: {e}\nExtracted candidate:\n{candidate[:2000]}"
                else:
                    last_error = "No JSON found in API output."

            except Exception as e:
                last_error = f"Validation failed: {e}"

        except RuntimeError as e:
            last_error = str(e)

        # If we get here, retry (if attempts remain)
        if attempt < max_retries:
            print(f"Retrying API call (attempt {attempt + 1}/{max_retries}) after short backoff...")
            time.sleep(1.5)
        else:
            break

    # If we exit the loop without returning, raise an error with helpful debug info
    raise RuntimeError(f"Failed to generate valid MCQs. Last error: {last_error}")


def _validate_mcq_list(mcqs):
    """
    Validate and normalize the list of MCQs returned by the API.
    Returns a clean list or raises ValueError on problems.
    """
    if not isinstance(mcqs, list):
        raise ValueError("MCQs is not a list.")
    clean = []
    for i, item in enumerate(mcqs):
        if not isinstance(item, dict):
            raise ValueError(f"MCQ #{i} is not an object.")
        q = item.get("question")
        opts = item.get("options")
        corr = item.get("correct")

        if not q or not isinstance(q, str):
            raise ValueError(f"MCQ #{i} missing 'question' or it is not a string.")
        if not isinstance(opts, dict):
            raise ValueError(f"MCQ #{i} 'options' is missing or not an object.")
        # Ensure all four options exist and are strings
        for key in ["A", "B", "C", "D"]:
            if key not in opts or not isinstance(opts[key], str) or not opts[key].strip():
                raise ValueError(f"MCQ #{i} option '{key}' is missing or invalid.")
        if corr not in ["A", "B", "C", "D"]:
            raise ValueError(f"MCQ #{i} 'correct' must be one of A/B/C/D.")
        clean.append({
            "question": q.strip(),
            "options": {k: opts[k].strip() for k in ["A", "B", "C", "D"]},
            "correct": corr
        })
    return clean


def save_mcqs_to_file(mcqs, filename):
    results_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    # Save as pretty JSON
    with open(results_path, 'w', encoding="utf-8") as f:
        json.dump(mcqs, f, ensure_ascii=False, indent=2)
    return results_path


def create_pdf(mcqs, filename):
    """
    mcqs: list of dicts as returned by _validate_mcq_list
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for i, m in enumerate(mcqs, start=1):
        q_text = f"{i}. {m['question']}"
        pdf.multi_cell(0, 7, q_text)
        pdf.ln(1)
        for key in ["A", "B", "C", "D"]:
            opt_text = f"    {key}) {m['options'][key]}"
            pdf.multi_cell(0, 7, opt_text)
        pdf.ln(1)
        pdf.multi_cell(0, 7, f"Correct Answer: {m['correct']}")
        pdf.ln(6)

    pdf_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    pdf.output(pdf_path)
    return pdf_path


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate_mcqs():
    if 'file' not in request.files:
        return "No file part", 400

    file = request.files['file']

    if not (file and allowed_file(file.filename)):
        return "Invalid file format", 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    text = extract_text_from_file(file_path)

    if not text:
        return "Failed to extract text from the uploaded file.", 400

    try:
        num_questions = int(request.form.get('num_questions', '0'))
        if num_questions <= 0:
            return "Invalid number of questions requested.", 400
    except ValueError:
        return "Invalid number of questions.", 400

    try:
        mcqs = Question_mcqs_generator(text, num_questions, max_retries=1)
    except RuntimeError as e:
        # Provide a useful error page instead of blank results
        err = str(e)
        print("ERROR generating MCQs:", err)
        return render_template('error.html', error_message=err), 500

    # Save results
    txt_filename = f"generated_mcqs_{filename.rsplit('.', 1)[0]}.txt"
    pdf_filename = f"generated_mcqs_{filename.rsplit('.', 1)[0]}.pdf"

    save_mcqs_to_file(mcqs, txt_filename)
    create_pdf(mcqs, pdf_filename)

    # Render results — mcqs is a list of dicts
    return render_template('results.html', mcqs=mcqs, txt_filename=txt_filename, pdf_filename=pdf_filename)


@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    if not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
    # Set debug=False in production
    app.run(debug=True)
