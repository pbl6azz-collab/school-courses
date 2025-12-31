import os
import json
import hashlib
import uuid
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

TEACHER_PASSWORD = os.getenv('TEACHER_PASSWORD', 'default_password_change_me')
TEACHER_PASSWORD_HASH = hash_password(TEACHER_PASSWORD)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key')

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATA_DIR = 'data'
COURSES_FILE = os.path.join(DATA_DIR, 'courses.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
os.makedirs(DATA_DIR, exist_ok=True)

if not os.path.exists(COURSES_FILE):
    with open(COURSES_FILE, 'w', encoding='utf-8') as f:
        json.dump([
            {
                "id": "snake",
                "title": "Создай игру 'Змейка' на Python",
                "steps": [
                    {
                        "type": "lesson",
                        "title": "Установи PyGame",
                        "content": "Открой терминал и выполни:\n\npip install pygame",
                        "image": None
                    },
                    {
                        "type": "quiz",
                        "title": "Проверь себя",
                        "question": "Что делает 'pip install'?",
                        "options": ["Удаляет пакет", "Устанавливает пакет", "Обновляет Python", "Создаёт проект"],
                        "correct": 1
                    }
                ]
            }
        ], f, ensure_ascii=False, indent=2)

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    courses = load_json(COURSES_FILE)
    return render_template('index.html', courses=courses, username=session['username'])

@app.route('/course/<course_id>')
def course(course_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    courses = load_json(COURSES_FILE)
    course = next((c for c in courses if c['id'] == course_id), None)
    if not course:
        return "Курс не найден", 404

    users = load_json(USERS_FILE)
    progress = users.get(session['username'], {}).get('progress', {})
    completed_steps_raw = progress.get(course_id, [])
    completed_steps = []
    if isinstance(completed_steps_raw, list):
        for x in completed_steps_raw:
            try:
                completed_steps.append(int(x))
            except (ValueError, TypeError):
                pass

    return render_template('course.html', course=course, completed_steps=completed_steps)

@app.route('/mark_step', methods=['POST'])
def mark_step():
    if 'username' not in session:
        return jsonify(success=False)
    data = request.get_json()
    if not data:
        return jsonify(success=False)

    course_id = data.get('course_id')
    step_index = data.get('step_index')
    completed = data.get('completed', False)

    try:
        step_index = int(step_index)
    except (TypeError, ValueError):
        return jsonify(success=False)

    users = load_json(USERS_FILE)
    user = users.setdefault(session['username'], {})
    user_progress = user.setdefault('progress', {})
    course_progress = user_progress.setdefault(course_id, [])

    if completed and step_index not in course_progress:
        course_progress.append(step_index)
    elif not completed and step_index in course_progress:
        course_progress.remove(step_index)

    save_json(USERS_FILE, users)
    return jsonify(success=True)

# --- Ученики ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        users = load_json(USERS_FILE)
        if username in users and users[username].get('password') == password:
            session['username'] = username
            return redirect(url_for('index'))
        return render_template('login.html', error="Неверное имя или пароль")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            return render_template('register.html', error="Заполните все поля")
        users = load_json(USERS_FILE)
        if username in users:
            return render_template('register.html', error="Такой пользователь уже есть")
        users[username] = {'password': hash_password(password), 'progress': {}}
        save_json(USERS_FILE, users)
        session['username'] = username
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# --- Учитель ---
@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if hash_password(password) == TEACHER_PASSWORD_HASH:
            session['is_teacher'] = True
            return redirect(url_for('index'))
        return render_template('teacher_login.html', error="Неверный пароль учителя")
    return render_template('teacher_login.html')

@app.route('/teacher/logout')
def teacher_logout():
    session.pop('is_teacher', None)
    return redirect(url_for('index'))  # ← ИСПРАВЛЕНО: было url_url

@app.route('/teacher/add_course', methods=['GET', 'POST'])
def add_course():
    if not session.get('is_teacher'):
        return redirect(url_for('teacher_login'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            return render_template('add_course.html', error="Укажите название курса")
        course_id = title.lower().replace(' ', '_').replace('-', '_').replace('.', '')
        courses = load_json(COURSES_FILE)
        base_id = course_id
        counter = 1
        while any(c['id'] == course_id for c in courses):
            course_id = f"{base_id}_{counter}"
            counter += 1
        courses.append({
            "id": course_id,
            "title": title,
            "steps": []
        })
        save_json(COURSES_FILE, courses)
        return redirect(url_for('index'))
    return render_template('add_course.html')

@app.route('/teacher/edit/<course_id>', methods=['GET', 'POST'])
def edit_course(course_id):
    if not session.get('is_teacher'):
        return redirect(url_for('teacher_login'))
    courses = load_json(COURSES_FILE)
    course = next((c for c in courses if c['id'] == course_id), None)
    if not course:
        return "Курс не найден", 404

    if request.method == 'POST':
        course['title'] = request.form.get('title', course['title']).strip()
        steps = []
        step_ids = request.form.getlist('step_id')

        for step_id in step_ids:
            if step_id == 'new':
                step_type = request.form.get('type_new', 'lesson')
                title = request.form.get('title_new', '').strip()
                if step_type == 'quiz':
                    question = request.form.get('question_new', '').strip()
                    options_raw = request.form.get('options_new', '').strip()
                    options = [opt.strip() for opt in options_raw.split('\n') if opt.strip()]
                    try:
                        correct = int(request.form.get('correct_new', 1)) - 1
                    except:
                        correct = 0
                    if title and question and options:
                        steps.append({
                            "type": "quiz",
                            "title": title,
                            "question": question,
                            "options": options,
                            "correct": correct
                        })
                else:
                    content = request.form.get('content_new', '').strip()
                    image = None
                    image_file = request.files.get('image_new')
                    if image_file and allowed_file(image_file.filename):
                        filename = secure_filename(image_file.filename)
                        ext = filename.rsplit('.', 1)[1].lower()
                        unique_name = f"{uuid.uuid4().hex}.{ext}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                        image_file.save(filepath)
                        image = f"uploads/{unique_name}"
                    if title or content or image:
                        steps.append({
                            "type": "lesson",
                            "title": title,
                            "content": content,
                            "image": image
                        })
            else:
                try:
                    idx = int(step_id)
                    if idx < len(course['steps']):
                        step = course['steps'][idx]
                        step_type = step.get('type', 'lesson')
                        title = request.form.get(f'title_{step_id}', '').strip()
                        if step_type == 'quiz':
                            question = request.form.get(f'question_{step_id}', step.get('question', '')).strip()
                            options_raw = request.form.get(f'options_{step_id}', '\n'.join(step.get('options', []))).strip()
                            options = [opt.strip() for opt in options_raw.split('\n') if opt.strip()]
                            try:
                                correct = int(request.form.get(f'correct_{step_id}', step.get('correct', 0) + 1)) - 1
                            except:
                                correct = step.get('correct', 0)
                            if title and question and options:
                                steps.append({
                                    "type": "quiz",
                                    "title": title,
                                    "question": question,
                                    "options": options,
                                    "correct": correct
                                })
                        else:
                            content = request.form.get(f'content_{step_id}', step.get('content', '')).strip()
                            image = step.get('image')
                            image_file = request.files.get(f'image_{step_id}')
                            if image_file and allowed_file(image_file.filename):
                                filename = secure_filename(image_file.filename)
                                ext = filename.rsplit('.', 1)[1].lower()
                                unique_name = f"{uuid.uuid4().hex}.{ext}"
                                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                                image_file.save(filepath)
                                image = f"uploads/{unique_name}"
                            if title or content or image:
                                steps.append({
                                    "type": "lesson",
                                    "title": title,
                                    "content": content,
                                    "image": image
                                })
                except (ValueError, IndexError):
                    continue

        course['steps'] = steps
        save_json(COURSES_FILE, courses)
        return redirect(url_for('course', course_id=course_id))

    return render_template('edit_course.html', course=course)

@app.route('/teacher/course/<course_id>/progress')
def teacher_progress(course_id):
    if not session.get('is_teacher'):
        return redirect(url_for('teacher_login'))
    
    courses = load_json(COURSES_FILE)
    course = next((c for c in courses if c['id'] == course_id), None)
    if not course:
        return "Курс не найден", 404

    users = load_json(USERS_FILE)
    total_steps = len(course['steps'])
    
    progress_data = []
    for username, data in users.items():
        if username == 'teacher':
            continue
        user_progress = data.get('progress', {}).get(course_id, [])
        completed = set()
        if isinstance(user_progress, list):
            for x in user_progress:
                try:
                    completed.add(int(x))
                except (ValueError, TypeError):
                    pass
        progress_data.append({
            'username': username,
            'completed': completed,
            'total': total_steps,
            'count': len(completed)
        })
    
    progress_data.sort(key=lambda x: x['username'])
    
    return render_template('teacher_progress.html', course=course, progress_data=progress_data)
@app.route('/submit_quiz/<course_id>/<int:step_index>', methods=['POST'])
def submit_quiz(course_id, step_index):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    answer = request.form.get('answer')
    courses = load_json(COURSES_FILE)
    course = next((c for c in courses if c['id'] == course_id), None)
    if not course or step_index >= len(course['steps']):
        return "Курс или шаг не найден", 404

    step = course['steps'][step_index]
    if step.get('type') != 'quiz':
        return "Это не тест", 400

    correct = step.get('correct', -1)
    try:
        user_answer = int(answer)
    except (TypeError, ValueError):
        user_answer = -1

    # Сохраняем прогресс, только если ответ правильный
    if user_answer == correct:
        users = load_json(USERS_FILE)
        user = users.setdefault(session['username'], {})
        user_progress = user.setdefault('progress', {})
        course_progress = user_progress.setdefault(course_id, [])
        if step_index not in course_progress:
            course_progress.append(step_index)
        save_json(USERS_FILE, users)

    # Перенаправляем обратно на курс
    return redirect(url_for('course', course_id=course_id))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
