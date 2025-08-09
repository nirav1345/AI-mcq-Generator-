<<<<<<< HEAD
# AI MCQ Generator

An AI-powered Multiple Choice Question (MCQ) generator web application built with Flask. It takes input text or uploaded documents and automatically generates MCQs in HTML, PDF, and TXT formats.

---

## Features

- Upload documents (PDF, DOCX) or input text directly to generate MCQs.
- View generated MCQs on the web page.
- Download MCQs as PDF or TXT files.
- Uses AI to parse and generate meaningful multiple-choice questions.
- Simple and clean user interface with static assets (CSS, SVG).

---

## Project Structure

project-folder/
│
├── app.py               # Main Flask application
├── README.md            # This README file
├── .env                 # Environment variables (API keys, etc.)
├── .gitignore           # Git ignore file
│
├── static/              # Static files like CSS, images, and SVG
│   ├── background.svg
│   ├── index.css
│   └── result.css
│
└── templates/           # HTML templates for Flask
├── index.html
└── results.html

---

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Installation Steps

1. Clone the repository (or download the project folder):

bash
git clone https://github.com/your-username/AI-mcq-Generator.git
cd AI-mcq-Generator

2.	Create and activate a virtual environment (recommended):

On macOS/Linux:

python3 -m venv venv
source venv/bin/activate

On Windows:

python -m venv venv
venv\Scripts\activate

3.	Install required Python packages:

pip install -r requirements.txt

If requirements.txt is not present, install manually:

pip install flask python-dotenv pdfplumber python-docx fpdf requests werkzeug

	
4.	Create a .env file in the project root and add your API key:

API_KEY=your_api_key_here

5.	Run the Flask application:

python app.py

6.	Open your web browser and navigate to:

Go to http://127.0.0.1:5000 to access the application.

Usage
	•	On the homepage, either input your text directly or upload a PDF or DOCX document.
	•	Submit the form to generate MCQs.
	•	View the generated questions on the results page.
	•	Download the MCQs as PDF or TXT files if desired.

⸻

Notes
	•	Ensure your API keys are valid and correctly set in the .env file.
	•	This app uses Flask’s development server, which is not suitable for production. For production deployment, use a WSGI server such as Gunicorn.
	•	Supported document types for upload: PDF and DOCX.
