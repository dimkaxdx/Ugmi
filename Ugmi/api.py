import re, bcrypt
from flask import request, jsonify, g
from functools import wraps

from Ugmi import app, db

from .models.user import User
from .models.comment import Comment
from .models.mark import Mark
from .decorators import parametrized




#Decorators:
def api_token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.get_json()
        if token is None:
            return jsonify(status = 'error', msg = 'Private area, token required.', code = 101), 401
        token = token.get('token')
        if token is None:
            return jsonify(status = 'error', msg = 'Private area, token required.', code = 101), 401
        user = User.check_api_token(token)
        if user is 'invalid':
            return jsonify(status = 'error', msg = 'Invalid token.', code = 102), 401
        if user is 'expired':
            return jsonify(status = 'error', msg = 'Token has expired.', code = 103), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper


@parametrized
def json_data_validation(f, req_data):
    @wraps(f)
    def wrapper(*args, **kwargs):
        data = request.get_json()
        if data is None:
            return jsonify(status = 'error', msg = 'Where is JSON?', code = 401), 400
        for field_name, data_type in req_data.items():
            field_data = data.get(field_name)
            if field_data is None:
                return jsonify(status = 'error', msg = ('Where is '+field_name+'?'), code = 402 ), 400
            if type(field_data) is not data_type:
                return jsonify(status = 'error', msg = ('Field '+field_name+' has type '+str(type(field_data))+' but expected '+str(data_type)+'.'), code = 402 ), 400
        return f(*args, **kwargs)
    return wrapper




#Error handlers:
@app.errorhandler(405)
def not_found_error(error):
    return jsonify(status = 'error', msg = 'Method not allowed.', code = None), 405




#Main views:
@app.route('/api/user/register', methods = ['POST'])
@json_data_validation( {'username': str, 'name': str, 'email': str, 'password': str} )
def api_register_user():
    data = request.get_json()
    username = data.get('username')
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
#VALIADTION
    name = name.strip().title()
    username = username.strip().lower()
    email = email.strip().lower()
    ok = True
    if( len(name) < 3 or len(name) > 64 or re.match("^[A-Za-zА-Яа-я ]*$", name) is None):
        ok = False
    if( len(username) < 3 or len(username) > 64 or re.match("^[A-Za-z0-9_]*$", username) is None):
        ok = False
    if( len(email) < 3 or len(email) > 64 or '@' not in email ):
        ok = False
    if( len(password) < 8 or len(password) > 256 ):
        ok = False
    if not ok:
        return jsonify(status = 'error', msg = 'Incorrect request.', code = 1), 400

    if User.query.filter_by(username = username).first() is not None:
        return jsonify(status = 'error', msg = 'Username already taken.', code = 2), 400
    if User.query.filter_by(email = email).first() is not None:
        return jsonify(status = 'error', msg = 'Email already registered.', code = 3), 400
#END VALIDATION
    password = bcrypt.hashpw(bytes(password, 'utf-8'), bcrypt.gensalt()).decode('utf-8')
    role = app.config['ROLE_DEFAULT']
    if email in app.config['ADMINS']:
        role = app.config['ROLE_ADMIN']
    user = User(name = name, email = email, username = username,
        password = password, role = role)
    db.session.add(user)
    db.session.commit()
    user.send_email_confirm_token()
    return jsonify(status = 'success', msg = 'User successfully registered.', code = None, token = user.get_api_token()), 200




@app.route('/api/user/info', methods = ['POST'])
@json_data_validation( {'username': str} )
@api_token_required
def api_get_info_about_user():
    username = request.get_json().get('username')
    user = User.query.filter_by(username = username).first()
    if user is None:
        return jsonify(status = 'error', msg = ("User with username '" + username + "' not found."), code = 1), 404
    return jsonify(status = 'success', msg = ('Info about user ' + username), code = None,
        id = str(user.id), username = user.username, email = user.email, name = user.name, role = user.prefix), 200





@app.route('/api/user/login', methods = ['POST'])
@json_data_validation( {'username': str, 'password': str} )
def api_auth_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username = username).first()
    if user is None:
        return jsonify(status = 'error', msg = ("User with username '" + username + "' not found."), code = 2), 404
    if not user.auth(password):
        return jsonify(status = 'error', msg = 'Incorrect password.', code = 3), 401
    return jsonify(status = 'success', msg = 'Successfully authorized.', code = None, token = user.get_api_token()), 200





#Comments:

@app.route('/api/comment/add', methods = ['POST'])
@json_data_validation( {'stars': int, 'body': str, 'mark_id': int} )
@api_token_required
def api_add_comment():
    data = request.get_json()
    stars = data.get('stars')
    body = data.get('body')
    mark_id = data.get('mark_id')
#VALIDATION:
    if (stars < 0 or stars > 5) or (len(body) > 2048):
        return jsonify(status = 'error', msg = 'Incorrect request.', code = 1), 400
    mark = Mark.query.get(mark_id)
    if mark is None:
        return jsonify(status = 'error', msg = ('Mark with ID '+str(mark_id)+' not found.'), code = 2), 404
#END VALIADTION
    comment = Comment(body = body, stars = stars, user = g.user, mark = mark)
    db.session.add(comment)
    db.session.commit()
    return jsonify(status = 'success', msg = 'Comment successfully added.', code = None), 200




@app.route('/api/comment/get', methods = ['POST'])
@json_data_validation( {'mark_id': int, 'start': int, 'cnt': int} )
def api_get_comment():
    data = request.get_json()
    start = data.get('start')
    cnt = data.get('cnt')
    mark_id = data.get('mark_id')
#VALIADTION:
    mark = Mark.query.get(mark_id)
    if mark is None:
        return jsonify(status = 'error', msg = ('Mark with ID '+str(mark_id)+' not found.'), code = 1), 404
    n = len(mark.comments)
    if start > n or start < 0:
        return jsonify(status = 'error', msg = ('Cant start from '+str(start)+' bcs mark has only '+str(n)+' comments.'), code = 2), 400
#END VALIADTION
    finish = min(start+cnt, n)
    comments = []
    for i in range(start, finish):
        c = mark.comments[i]
        data = {}
        data['body'] = c.body
        data['name'] = c.user.name
        data['stars'] = c.stars
        comments.append(data)
    return jsonify(status = 'success', msg = ('Comments from '+str(start)+' to '+str(finish)), code = None, cnt = n, comments = comments), 200
