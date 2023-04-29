from flask_socketio import SocketIO, emit, send, join_room, leave_room
from data import db_session
from flask import render_template, redirect, request, Flask, abort, jsonify, make_response, session, url_for
from forms.registerform import RegisterForm
from forms.submit import SubmitForm
from forms.loginform import LoginForm
from data.users import User
from data.categories import Categories
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
import random
from string import ascii_uppercase
import openai

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'

socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)

rooms = {}
remember_data = []
openai.api_key = "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"

clicked = False


def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)

        if code not in rooms:
            break

    return code


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)


@app.route("/", methods=['GET', 'POST'])
def index():
    session.clear()
    form = SubmitForm()
    if form.validate_on_submit():
        return redirect('/login')
    return render_template("index.html", form=form)


@app.route("/home", methods=["POST", "GET"])
@login_required
def home():
    if request.method == "POST":
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)
        name = session["name"]

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)

        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, 'customers': [], "admin": name,
                           "status": False, "round": 1}
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)

        session["room"] = room
        session["points"] = 0

        return redirect("/lobby")

    return render_template("home.html")


@app.route('/register', methods=['GET', 'POST'])
def reqister():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Пароли не совпадают")
        db_sess = db_session.create_session()
        if db_sess.query(User).filter(User.email == form.email.data).first():
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Такой пользователь уже есть")
        user = User(
            name=form.name.data,
            email=form.email.data,
            about=form.about.data
        )
        user.set_password(form.password.data)
        db_sess.add(user)
        db_sess.commit()
        return redirect('/login')
    return render_template('register.html', title='Регистрация', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            session["name"] = user.name
            return redirect("/home")
        return render_template('login.html',
                               message="Неправильный логин или пароль",
                               form=form)
    return render_template('login.html', title='Авторизация', form=form)


@app.route('/lobby', methods=['GET', 'POST'])
@login_required
def lobby():
    room = session.get('room')
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

    return render_template('lobby.html', code=room, name=session["name"], room_data=rooms[room])


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.errorhandler(400)
def bad_request(_):
    return make_response(jsonify({'error': 'Bad Request'}), 400)


@socketio.on("connect")
def connect():
    room = session.get("room")
    name = session.get("name")
    points = session.get("points")
    global remember_data

    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return

    for person in remember_data:
        if name in person:
            if name != rooms[room]["admin"]:
                join_room(room)
                rooms[room]["members"] += 1
                rooms[room]["customers"].append(person)
                session["points"] = int(person.split()[-1])
            else:
                join_room(room)
                rooms[room]["members"] += 1
                rooms[room]["customers"].append(name)
            send(rooms[room]["customers"], to=room)
            print(f"{name} joined room {room}", rooms)
            return

    remember_data.append(name)

    print(room, name, points, remember_data, "\n", rooms)

    if name != rooms[room]["admin"]:
        if name not in list(map(lambda x: x.split()[0], rooms[room]["customers"])):
            join_room(room)
            rooms[room]["members"] += 1
            rooms[room]["customers"].append(f"{name} {points}")
    else:
        if name not in rooms[room]["customers"]:
            join_room(room)
            rooms[room]["members"] += 1
            rooms[room]["customers"].append(name)
    send(rooms[room]["customers"], to=room)
    print(f"{name} joined room {room}", rooms)


@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    new_name = ""

    global remember_data
    for person in rooms[room]["customers"]:
        if name in person:
            new_name = rooms[room]['customers'][rooms[room]['customers'].index(person)]
    for person in remember_data:
        if name in person:
            remember_data[remember_data.index(person)] = new_name

    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["admin"] != name:
            for person in rooms[room]['customers']:
                if name in person:
                    del rooms[room]['customers'][rooms[room]['customers'].index(person)]
        else:
            del rooms[room]['customers'][rooms[room]['customers'].index(name)]
        if rooms[room]["members"] <= 0:
            del rooms[room]
            return
    send(rooms[room]["customers"], to=room)
    print(f"{name} has left the room {room}", rooms)


@socketio.on("start_game")
def db_edit(data):
    room = session["room"]

    rooms[room]["status"] = True
    rooms[room]["data_for_lobby"] = data
    emit("reload", to=room)


@socketio.on("start_game_by_ChatGPT")
def db_edit(data):
    room = session["room"]

    rooms[room]["status"] = True
    rooms[room]["data_for_lobby"] = data

    for i in data:
        try:
            if not data[i]["name"]:
                continue

            content = data[i]["name"]

            messages = [{"role": "system",
                         "content": "I write you the name of the category, and you come up with 5 answers and 5 questions "
                                    "for this category for \"your game\", that is, the first question should be "
                                    "the simplest, the fifth the most difficult.\n"
                                    "Give the answers only in the format:\n"
                                    "Question 1 : ...\n"
                                    "Question 2: ...\n"
                                    "Question 3: ...\n"
                                    "Question 4: ...\n"
                                    "Question 5: ...\n"
                                    "Answer 1: ...\n"
                                    "Answer 2: ...\n"
                                    "Answer 3: ...\n"
                                    "Answer 4: ...\n"
                                    "Answer 5: ..."}, {"role": "user", "content": content}]

            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages
            )

            def rebild_sistem(data):
                if data != "":
                    return data.split(": ")[-1]
                else:
                    return False

            chat_response = list(map(rebild_sistem, completion.choices[0].message.content.split("\n")))
            mass = [[chat_response[i], chat_response[i + 6], False] for i in range(5)]
            for j in range(5):
                rooms[room]["data_for_lobby"][i][str(j)] = mass[j]

        except IndexError:
            continue

        else:
            continue

    print(rooms[room]["data_for_lobby"])

    emit("reload", to=room)


@socketio.on("question-click")
def question_click(data):
    room = session.get("room")
    emit("show-model", data, to=room)


@socketio.on("show-gif")
def question_click(data):
    room = session.get("room")
    if data:
        emit("show-winner-event", to=room)
    else:
        emit("show-looser-event", to=room)


@socketio.on("i-know-answer-click")
def return_name():
    room = session.get("room")
    name = session.get("name")

    emit("return-the-name-of-the-first-person-who-clicked", name, to=room)


@socketio.on("add-points")
def add_points(data):
    room = session.get("room")

    session["points"] += data[1]

    points = session.get("points")

    for person in rooms[room]["customers"]:
        if person.split()[0] == data[0]:
            rooms[room]["customers"][rooms[room]["customers"].index(person)] = f"{person.split()[0]} {points}"
            send(rooms[room]["customers"], to=room)


@socketio.on("round-is-over")
def round_is_over():
    room = session.get("room")
    rooms[room]["status"] = False
    rooms[room]["round"] += 1
    emit("reload", to=room)


@socketio.on("game-is-over")
def game_over():
    room = session.get("room")

    def proverka(element):
        if len(element.split(" ")) == 1:
            return -100000
        else:
            return int(element.split(" ")[-1])

    list_points = list(map(proverka, rooms[room]["customers"]))
    winner = rooms[room]["customers"][list_points.index(max(list_points))].split(" ")[0]
    print(winner)
    emit("winner-is", [winner, max(list_points)], to=room)


def main():
    db_session.global_init("db/users.db")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)


if __name__ == '__main__':
    main()
