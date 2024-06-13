from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, TextAreaField
from wtforms.validators import DataRequired, Length, Email
from nltk.tokenize import sent_tokenize
from collections import Counter
from bs4 import BeautifulSoup
import requests
import os
import pyttsx3
from pptx import Presentation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
import tempfile
import pytesseract
from PIL import Image

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Specify the path to the Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'  # Update this path as needed

app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOADED_PHOTOS_DEST'] = 'uploads'

# Ensure the upload directory exists
if not os.path.exists(app.config['UPLOADED_PHOTOS_DEST']):
    os.makedirs(app.config['UPLOADED_PHOTOS_DEST'])

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=True)
    education = db.Column(db.String(100), nullable=True)

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        new_user = User(username=form.username.data, email=form.email.data, password=form.password.data)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data, password=form.password.data).first()
        if user:
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/image-summarization', methods=['GET', 'POST'])
def image_summarization():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        if 'photo' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['photo']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file:
            file_path = os.path.join(app.config['UPLOADED_PHOTOS_DEST'], file.filename)
            file.save(file_path)

            text = extract_text_from_image(file_path)
            num_sentences = int(request.form['num_sentences'])
            summary = summarize_text(text, num_sentences)
            
            session['summary'] = summary
            return redirect(url_for('summary'))
    return render_template('image_summarization.html')

@app.route('/text-summarization', methods=['GET', 'POST'])
def text_summarization():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        text = request.form['text']
        num_sentences = int(request.form['num_sentences'])
        summary = summarize_text(text, num_sentences)
        
        session['summary'] = summary
        return redirect(url_for('summary'))
    return render_template('text_summarization.html')

@app.route('/summary')
def summary():
    if 'summary' not in session:
        return redirect(url_for('dashboard'))
    summary = session['summary']
    return render_template('summary.html', summary=summary)

@app.route('/download-pdf', methods=['POST'])
def download_pdf():
    summary_text = request.form['summary_text']
    
    # Create a BytesIO buffer to store PDF content
    buffer = BytesIO()
    
    # Create a PDF canvas
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Write the summary text to the PDF
    text_object = c.beginText(100, 750)
    for line in summary_text.split('\n'):
        text_object.textLine(line)
    c.drawText(text_object)
    
    # Save the PDF canvas to the buffer
    c.save()
    
    # Get the PDF content from the buffer
    pdf_data = buffer.getvalue()
    
    # Rewind the buffer
    buffer.seek(0)
    
    # Send the PDF data as a file attachment
    response = Response(
        pdf_data,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': 'attachment; filename=summary.pdf'
        }
    )
    return response

@app.route('/enter-url', methods=['GET', 'POST'])
def enter_url():
    if request.method == 'POST':
        url = request.form['url']
        # Redirect to the summarization page with the URL as a query parameter
        return redirect(url_for('summarize_website', url=url))
    return render_template('enter_url.html')

@app.route('/summarize-website', methods=['GET', 'POST'])
def summarize_website():
    if request.method == 'POST':
        url = request.form['url']
        num_sentences = int(request.form['num_sentences'])
        
        try:
            # Fetch the HTML content of the website
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for HTTP status codes indicating failure
            html_content = response.text
            
            # Extract text content from HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            text_content = ' '.join(soup.stripped_strings)
            
            # Summarize the text content
            summary = summarize_text(text_content, num_sentences)
            
            # Convert summary into a list of sentences
            sentences = sent_tokenize(summary)
            
            # Render the summary page with the summarized text and bullet points
            return render_template('website_summary.html', sentences=sentences)
        except Exception as e:
            # Handle errors
            error_message = f"An error occurred: {e}"
            flash(error_message, 'danger')
            return redirect(url_for('index'))

    return render_template('summarize_website.html')


@app.route('/download-pptx', methods=['POST'])
def download_pptx():
    summary_text = request.form['summary_text']
    prs = Presentation()
    slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(slide_layout)
    title = slide.shapes.title
    content = slide.placeholders[1]
    title.text = "Summary"
    content.text = summary_text
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.pptx')
    prs.save(temp.name)
    temp.seek(0)
    return send_file(temp.name, as_attachment=True, download_name='summary.pptx')

def extract_text_from_image(image_path):
    text = pytesseract.image_to_string(Image.open(image_path))
    return text

def summarize_text(text, num_sentences):
    sentences = sent_tokenize(text)
    if len(sentences) <= num_sentences:
        return text
    word_counts = Counter(word for sentence in sentences for word in sentence.split())
    sentence_scores = [(sum(word_counts[word] for word in sentence.split()), sentence) for sentence in sentences]
    top_sentences = sorted(sentence_scores, reverse=True)[:num_sentences]
    top_sentences.sort(key=lambda x: sentences.index(x[1]))
    summary = ' '.join(sentence for score, sentence in top_sentences)
    return summary

@app.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    if 'summary' in session:
        summary = session['summary']
        engine = pyttsx3.init()
        engine.say(summary)
        engine.runAndWait()
        return redirect(url_for('summary'))
    else:
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
