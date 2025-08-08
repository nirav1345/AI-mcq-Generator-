from dotenv import load_dotenv
import os
import re
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
        text = ' '.join([para.text for para in doc.paragraphs])
        return text.strip()
    elif ext == 'txt':
        with open(file_path, 'r', encoding="utf-8") as file:
            return file.read().strip()
    return None


def Question_mcqs_generator(input_text, num_questions):
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    You are an AI assistant helping the user generate multiple-choice questions (MCQs) based on the following text:
    '{input_text}'
    Please generate {num_questions} MCQs from the text. Each question should have:
    - A clear question
    - Four answer options (labeled A, B, C, D)
    - The correct answer clearly indicated
    Format:
    ## MCQ
    Question: [question]
    A) [option A]
    B) [option B]
    C) [option C]
    D) [option D]
    Correct Answer: [correct option]
    """

    payload = {
        "model": "sonar-reasoning-pro",
        "messages": [
            {"role": "system", "content": "You are an MCQ generator."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Error calling Perplexity API: {str(e)}"

    try:
        data = response.json()
        if "error" in data:
            return f"Error from Perplexity API: {data['error'].get('message', 'Unknown error')}"
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        return f"Unexpected API response: {response.text}"


def save_mcqs_to_file(mcqs, filename):
    results_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    with open(results_path, 'w', encoding="utf-8") as f:
        f.write(mcqs)
    return results_path


def create_pdf(mcqs, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for mcq in mcqs.split("## MCQ"):
        if mcq.strip():
            pdf.multi_cell(0, 10, mcq.strip())
            pdf.ln(5)

    pdf_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    pdf.output(pdf_path)
    return pdf_path


def parse_mcqs(mcq_text):
    mcq_list = []
    blocks = [b.strip() for b in mcq_text.split("## MCQ") if b.strip()]
    print(f"DEBUG: Found {len(blocks)} MCQ blocks")

    for i, block in enumerate(blocks):
        print(f"\nDEBUG: Parsing block {i}:\n{block}\n")

        question_match = re.search(r"Question:\s*(.+)", block)
        question = question_match.group(1).strip() if question_match else None

        options = {}
        for opt in ['A', 'B', 'C', 'D']:
            opt_match = re.search(rf"{opt}\)\s*(.+)", block)
            options[opt] = opt_match.group(1).strip() if opt_match else None

        correct_match = re.search(r"Correct Answer:\s*([ABCD])", block)
        correct = correct_match.group(1).strip() if correct_match else None

        if not question:
            print(f"DEBUG: Skipped block {i} - missing question")
            continue
        if None in options.values():
            print(f"DEBUG: Skipped block {i} - missing one or more options")
            continue
        if not correct:
            print(f"DEBUG: Skipped block {i} - missing correct answer")
            continue

        mcq_list.append({
            "question": question,
            "options": options,
            "correct": correct
        })

    print(f"\nDEBUG: Parsed {len(mcq_list)} MCQs successfully\n")
    return mcq_list


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate_mcqs():
    if 'file' not in request.files:
        return "No file part"

    file = request.files['file']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        text = extract_text_from_file(file_path)

        if text:
            num_questions = int(request.form['num_questions'])
            mcqs_text = Question_mcqs_generator(text, num_questions)

            print("\n=== RAW MCQ TEXT FROM API ===\n")
            print(mcqs_text)
            print("\n=== END RAW MCQ TEXT ===\n")

            if mcqs_text.startswith("Error"):
                return mcqs_text  # Show API error message directly

            txt_filename = f"generated_mcqs_{filename.rsplit('.', 1)[0]}.txt"
            pdf_filename = f"generated_mcqs_{filename.rsplit('.', 1)[0]}.pdf"

            save_mcqs_to_file(mcqs_text, txt_filename)
            create_pdf(mcqs_text, pdf_filename)

            mcqs = parse_mcqs(mcqs_text)  # parse into structured data for template

            print(f"DEBUG: Parsed {len(mcqs)} MCQs")
            for idx, mcq in enumerate(mcqs):
                print(f"DEBUG MCQ {idx+1}: Q: {mcq['question']}, Correct: {mcq['correct']}")

            return render_template('results.html', mcqs=mcqs, txt_filename=txt_filename, pdf_filename=pdf_filename)

    return "Invalid file format"


@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    if not os.path.exists(app.config['RESULTS_FOLDER']):
        os.makedirs(app.config['RESULTS_FOLDER'])
    app.run(debug=True)