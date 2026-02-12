from flask import Flask, request, redirect, url_for, render_template, flash, abort, jsonify
from werkzeug.utils import secure_filename
import os
import uuid
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
try:
    from flask_socketio import SocketIO, join_room, leave_room, emit
    SOCKETIO_ENABLED = True
except Exception:
    SOCKETIO_ENABLED = False
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, DateField, SelectField, SelectMultipleField, DecimalField, FileField
from wtforms.validators import InputRequired, Email, Length, EqualTo, ValidationError, Regexp, Optional
from flask_wtf.file import FileField, FileAllowed, FileSize
import re
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps
from datetime import date, datetime

# --- Initialize app ---
app = Flask(__name__)

# Security settings
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')  # change in production
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour CSRF token validity

# Upload settings
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['TRIP_COVERS_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'trip_covers')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_EXTENSIONS'] = ['.jpg', '.jpeg', '.png']
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Ensure upload directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TRIP_COVERS_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_trip_cover(file):
    """Save an uploaded trip cover image and return the filename."""
    try:
        if not file:
            return None
        
        if not hasattr(file, 'filename'):
            app.logger.error('Invalid file object: no filename attribute')
            return None
            
        if not allowed_file(file.filename):
            app.logger.error(f'Invalid file type: {file.filename}')
            return None
            
        # Generate a secure filename with UUID to prevent duplicates
        try:
            ext = file.filename.rsplit('.', 1)[1].lower()
        except IndexError:
            app.logger.error(f'Invalid filename format: {file.filename}')
            return None
            
        filename = f"{str(uuid.uuid4())}.{ext}"
        
        # Ensure the upload directory exists
        os.makedirs(app.config['TRIP_COVERS_FOLDER'], exist_ok=True)
        
        # Save the file
        file_path = os.path.join(app.config['TRIP_COVERS_FOLDER'], filename)
        try:
            file.save(file_path)
        except Exception as e:
            app.logger.error(f'Error saving file: {str(e)}')
            if os.path.exists(file_path):
                os.remove(file_path)
            return None
        
        # Return the relative path for database storage
        return f"uploads/trip_covers/{filename}"
        
    except Exception as e:
        app.logger.error(f'Unexpected error in save_trip_cover: {str(e)}')
        return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Database config and init ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tripmates.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Login manager ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- SocketIO (optional) ---
socketio = None
if SOCKETIO_ENABLED:
    socketio = SocketIO(app, cors_allowed_origins='*')

# --- User model ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))





# --- Trip model ---
class Trip(db.Model):
    """
    Represents a travel trip. 
    Connected to User (who created it) and optionally a Group.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # The owner of the trip
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True) # Optional group link
    
    title = db.Column(db.String(120), nullable=False)
    destination = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True)
    share_token = db.Column(db.String(64), unique=True, nullable=True)

    # Relationships: This allows us to access trip.owner easily
    owner = db.relationship('User', backref='trips')

    def generate_share_token(self):
        """Generate a secure random token for trip sharing."""
        import secrets
        self.share_token = secrets.token_urlsafe(32)
        return self.share_token

    def get_share_url(self):
        """Get the full URL for sharing this trip."""
        from flask import url_for
        if not self.share_token:
            self.generate_share_token()
            db.session.commit()
        return url_for('share_trip', trip_id=self.id, token=self.share_token, _external=True)


# --- Itinerary model ---
class ItineraryItem(db.Model):
    """
    Represents a specific activity or stop within a Trip.
    """
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    datetime = db.Column(db.DateTime, nullable=False) # Date and time of the activity
    location = db.Column(db.String(200), nullable=True)
    cost = db.Column(db.Numeric(10,2), nullable=True)
    tags = db.Column(db.String(255), nullable=True)

    trip = db.relationship('Trip', backref='itinerary_items')


# --- Phase 3: Groups & Membership ---
class Group(db.Model):
    """
    Represents a travel group. Users can join groups to share trips and chat.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # The person who created the group
    join_token = db.Column(db.String(64), unique=True, nullable=False) # Token used for invitation links
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    approval_required = db.Column(db.Boolean, nullable=False, default=False) # New: admin must approve

    admin = db.relationship('User', backref='owned_groups')
    members = db.relationship('GroupMember', backref='group', cascade='all, delete-orphan')
    messages = db.relationship('GroupMessage', 
                             backref=db.backref('group', lazy='joined'),
                             lazy='dynamic',
                             cascade='all, delete-orphan',
                             order_by='GroupMessage.timestamp.asc()')

    def generate_join_token(self):
        """Generate a secure random token for group joining."""
        import secrets
        self.join_token = secrets.token_urlsafe(32)
        return self.join_token

    def get_join_url(self):
        """Get the full URL for joining this group."""
        from flask import url_for
        return url_for('join_group', token=self.join_token, _external=True)

    def get_member_count(self):
        """Get the total number of members in the group."""
        return GroupMember.query.filter_by(group_id=self.id).count()

    def is_member(self, user_id):
        """Check if a user is a member of this group."""
        return GroupMember.query.filter_by(group_id=self.id, user_id=user_id, status='active').first() is not None


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    status = db.Column(db.String(20), nullable=False, default='active') # New: 'active' or 'pending'
    joined_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

    user = db.relationship('User', backref='group_memberships')

    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='unique_group_member'),
    )


class GroupMessage(db.Model):
    """Model for group chat messages with support for text, media, and location."""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    media_filename = db.Column(db.String(255), nullable=True)
    location_lat = db.Column(db.Float, nullable=True)
    location_lng = db.Column(db.Float, nullable=True)
    location_label = db.Column(db.String(255), nullable=True)

    user = db.relationship('User', backref='group_messages')


# --- Phase 5: Expenses & Budgeting ---
# Many-to-Many relationship table: Links Expenses to multiple Users (participants)
expense_participants = db.Table('expense_participants',
    db.Column('expense_id', db.Integer, db.ForeignKey('expense.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class Expense(db.Model):
    """
    Represents a single expense within a trip.
    Tracks who paid (payer) and who shared the cost (participants).
    """
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    trip = db.relationship('Trip', backref='expenses')
    payer = db.relationship('User', foreign_keys=[payer_id])
    # Secondary table 'expense_participants' handles the many-to-many link
    participants = db.relationship('User', secondary=expense_participants, backref='expenses_participated')



@app.route('/groups/<int:group_id>/messages')
@login_required
def get_group_messages(group_id):
    group = Group.query.get_or_404(group_id)
    # Check if the current user is a member of the group
    if not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
        return jsonify({'error': 'Not a member'}), 403
    
    # Fetch the last 200 messages
    messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.timestamp.desc()).limit(200).all()
    
    message_list = []
    for msg in messages:
        message_list.append({
            'id': msg.id,
            'user': msg.user.name,
            'user_id': msg.user_id,
            'text': msg.message,
            'timestamp': msg.timestamp.isoformat(),
            'media_filename': msg.media_filename,
            'location_lat': msg.location_lat,
            'location_lng': msg.location_lng,
            'location_label': msg.location_label,
        })
    return jsonify(message_list)


@app.route('/groups/<int:group_id>/upload', methods=['POST'])
@login_required
def upload_group_media(group_id):
    grp = Group.query.get_or_404(group_id)
    if not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
        return jsonify({'error': 'not a member'}), 403
    # Quick content-length check (Flask will also enforce MAX_CONTENT_LENGTH)
    if request.content_length is not None and request.content_length > app.config.get('MAX_CONTENT_LENGTH', 0):
        return jsonify({'error': 'file too large'}), 413
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'empty filename'}), 400
    filename = secure_filename(f.filename)
    # validate extension
    if not allowed_file(filename):
        return jsonify({'error': 'file type not allowed'}), 400
    # prefix with uuid to avoid collisions
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    try:
        f.save(save_path)
    except Exception as e:
        app.logger.exception('Failed to save uploaded file')
        return jsonify({'error': 'failed to save file'}), 500
    from datetime import datetime
    msg = GroupMessage(
        group_id=group_id,
        user_id=current_user.id,
        message='',
        media_filename=unique_name
    )
    db.session.add(msg)
    db.session.commit()
    # emit
    room = f'group_{group_id}'
    media_url = url_for('static', filename=f'uploads/{msg.media_filename}')
    payload = {'id': msg.id, 'user': current_user.name, 'user_id': current_user.id, 'text': '', 'timestamp': msg.timestamp.isoformat(), 'media_filename': msg.media_filename, 'media_url': media_url}
    if SOCKETIO_ENABLED and socketio is not None:
        socketio.emit('message', payload, room=room)
    return jsonify({'ok': True, 'message': payload})




if SOCKETIO_ENABLED:
    @socketio.on('connect')
    def handle_connect():
        sid = request.sid if hasattr(request, 'sid') else 'unknown'
        app.logger.info(f"SocketIO: connect sid={sid} user_authenticated={current_user.is_authenticated}")
        if not current_user.is_authenticated:
            app.logger.info('SocketIO: unauthenticated socket connection')

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid if hasattr(request, 'sid') else 'unknown'
        app.logger.info(f"SocketIO: disconnect sid={sid} user={getattr(current_user,'id',None)}")

    @socketio.on('join')
    def handle_join(data):
        group_id = data.get('group')
        if not group_id:
            emit('error', {'message': 'missing group id'})
            return
        app.logger.info(f"SocketIO: join request group={group_id} user={getattr(current_user,'id',None)}")
        # verify membership
        if not current_user.is_authenticated or not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
            emit('error', {'message': 'not a member or not authenticated'})
            return
        room = f'group_{group_id}'
        join_room(room)
        app.logger.info(f"SocketIO: {current_user.name} joined room {room}")
        # notify the joining client that they have joined
        emit('joined', {'group': group_id})
        # broadcast status to room
        emit('new_message', {
            'text': f'👋 {current_user.name} joined the chat',
            'is_status': True,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }, room=room)

    @socketio.on('leave')
    def handle_leave(data):
        group_id = data.get('group')
        app.logger.info(f"SocketIO: leave request group={group_id} user={getattr(current_user,'id',None)}")
        if not group_id:
            return
        room = f'group_{group_id}'
        leave_room(room)
        app.logger.info(f"SocketIO: {getattr(current_user,'name',None)} left room {room}")
        # notify client and broadcast
        emit('new_message', {
            'text': f'🚪 {getattr(current_user,"name", "A user")} left the chat',
            'is_status': True,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }, room=room)

    @socketio.on('message')
    def handle_message(data):
        group_id = data.get('group')
        text = data.get('text')
        app.logger.info(f"SocketIO: message incoming group={group_id} user={getattr(current_user,'id',None)} text_present={bool(text)}")
        if not group_id or not text:
            emit('error', {'message': 'group and text required'})
            return
        # membership check
        if not current_user.is_authenticated or not GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first():
            emit('error', {'message': 'not a member or not authenticated'})
            return
        from datetime import datetime
        msg = GroupMessage(
            group_id=group_id,
            user_id=current_user.id,
            message=text
        )
        db.session.add(msg)
        db.session.commit()
        app.logger.info(f"SocketIO: message saved id={msg.id} group={group_id} user={current_user.id}")
        room = f'group_{group_id}'
        emit('new_message', {
            'id': msg.id, 
            'user': current_user.name, 
            'user_id': current_user.id, 
            'text': text, 
            'timestamp': msg.timestamp.isoformat() + 'Z'
        }, room=room)


class GroupForm(FlaskForm):
    name = StringField('Group Name', validators=[
        InputRequired(), 
        Length(1, 120),
        Regexp(r'^[\w\s-]+$', message='Group name can only contain letters, numbers, spaces, and hyphens')
    ])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Create Group')

# --- Forms ---
class RegistrationForm(FlaskForm):
    name = StringField('Name', validators=[InputRequired(), Length(1,50)])
    # custom validator enforces lowercase, allowed characters, and domain rules
    def validate_email_lower_and_format(form, field):
        v = (field.data or '').strip()
        # enforce lowercase only
        if any(c.isupper() for c in v):
            raise ValidationError('Email must be all lowercase.')
        # strict regex: starts with letter/number, then letters/digits/._- before @,
        # domain part must have at least one dot and only lowercase letters/digits/dot/hyphen
        pattern = re.compile(r'^[a-z0-9][a-z0-9._-]*@[a-z0-9.-]+\.[a-z]{2,}$')
        if not pattern.fullmatch(v):
            raise ValidationError('Enter a valid email address (start with letter/number; allowed characters before @: letters, digits, underscore, dot, hyphen; domain must include a dot and be lowercase).')

    email = StringField('Email', validators=[InputRequired(), validate_email_lower_and_format])
    password = PasswordField('Password', validators=[InputRequired(), Length(8,128)])
    confirm = PasswordField('Confirm Password', validators=[InputRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_email(self, field):
        # normalize
        v = (field.data or '').strip().lower()
        if User.query.filter_by(email=v).first():
            raise ValidationError('Email already registered.')

    def validate_password(self, field):
        pwd = field.data or ''
        # require min 8, uppercase, lowercase, digit, special char
        if len(pwd) < 8:
            raise ValidationError('Password must be at least 8 characters.')
        if not re.search(r'[A-Z]', pwd):
            raise ValidationError('Password must include at least one uppercase letter.')
        if not re.search(r'[a-z]', pwd):
            raise ValidationError('Password must include at least one lowercase letter.')
        if not re.search(r'[0-9]', pwd):
            raise ValidationError('Password must include at least one number.')
        if not re.search(r'[^A-Za-z0-9]', pwd):
            raise ValidationError('Password must include at least one special character.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[InputRequired()])
    password = PasswordField('Password', validators=[InputRequired()])
    submit = SubmitField('Login')


class TripForm(FlaskForm):
    # Trip title: required, minimum 3 chars
    title = StringField('Title', validators=[InputRequired(), Length(min=3, max=120)])
    # Destination: only letters and spaces allowed
    # Allow common punctuation (commas, periods, hyphens) and numbers in destinations (e.g. "St. Louis", "I-95")
    destination = StringField('Destination', validators=[InputRequired(), Regexp(r'^[A-Za-z0-9\s,\.\-]+$', message='Destination may contain letters, numbers, spaces, commas, periods and hyphens.'), Length(max=120)])
    start_date = DateField('Start date', validators=[InputRequired()], format='%Y-%m-%d')
    end_date = DateField('End date', validators=[InputRequired()], format='%Y-%m-%d')
    # Description: optional but limited length
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    # Cover image: optional, but must be an image file
    cover_image = FileField('Cover Image', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Please upload only jpg or png images.')
    ])
    # Group selection: optional, allows linking trip to a group
    group_id = SelectField('Group (Optional)', coerce=int, validators=[Optional()], choices=[])
    # Add submit button

    def validate_start_date(form, field):
        # start date must be today or in the future
        if field.data is None:
            return
        if field.data < date.today():
            raise ValidationError('Start date cannot be in the past.')

    def validate_end_date(form, field):
        # end date must be same or after start date
        if field.data is None or form.start_date.data is None:
            return
        if field.data < form.start_date.data:
            raise ValidationError('End date must be the same or after the start date.')
    # Single submit button (template renders its own button)
    submit = SubmitField('Create Trip')


class ItineraryForm(FlaskForm):
    title = StringField('Title', validators=[InputRequired(), Length(min=1, max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    date = DateField('Date', validators=[InputRequired()], format='%Y-%m-%d')
    time = StringField('Time', validators=[Optional()], render_kw={"type": "time"})
    location = StringField('Location')
    cost = StringField('Cost')
    tags = StringField('Tags (comma separated)')
    submit = SubmitField('Save')

    def validate_date(self, field):
        """Validate that the itinerary date falls within the trip's date range."""
        if hasattr(self, 'trip') and self.trip:
            if field.data < self.trip.start_date:
                raise ValidationError('The itinerary date cannot be before the trip\'s start date')
            if field.data > self.trip.end_date:
                raise ValidationError('The itinerary date cannot be after the trip\'s end date')

    def validate_time(self, field):
        """Validate time format if provided."""
        if not field.data:
            return
        try:
            from datetime import datetime
            datetime.strptime(field.data, '%H:%M')
        except ValueError:
            raise ValidationError('Invalid time format. Please use HH:MM format.')

    def validate_cost(form, field):
        if field.data:
            try:
                float(field.data)
            except Exception:
                raise ValidationError('Cost must be a number, e.g. 12.50')


class ExpenseForm(FlaskForm):
    title = StringField('Title', validators=[InputRequired(), Length(min=1, max=200)])
    amount = StringField('Amount (₹)', validators=[InputRequired()])
    payer = SelectField('Payer', coerce=int, validators=[InputRequired()])
    participants = SelectMultipleField('Participants', coerce=int, validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save')

    def validate_amount(form, field):
        try:
            val = float(field.data)
            if val < 0:
                raise ValidationError('Amount must be non-negative.')
        except Exception:
            raise ValidationError('Enter a numeric amount, e.g. 23.50')

def is_trip_member(trip_id, user_id):
    # trip owner or group member
    t = Trip.query.get(trip_id)
    if not t:
        return False
    if t.user_id == user_id:
        return True
    # if trip is linked to a group, check group membership
    if getattr(t, 'group_id', None):
        if GroupMember.query.filter_by(group_id=t.group_id, user_id=user_id).first():
            return True
    return False

def compute_balances(trip_id):
    """
    Calculate how much each user owes or is owed for a specific trip.
    Returns a dictionary: user_id -> balance
    Positive balance: User is owed money.
    Negative balance: User owes money.
    """
    # Fetch all expenses related to this trip
    expenses = Expense.query.filter_by(trip_id=trip_id).all()
    balances = {}

    for expense in expenses:
        total_amount = float(expense.amount)
        # Participants are the people sharing this expense
        participants = expense.participants or []
        
        if len(participants) > 0:
            share_per_person = total_amount / len(participants)
        else:
            # If no participants, the payer pays for themselves (no split)
            share_per_person = 0

        # 1. Update Payer's Balance
        # The payer initially gets the full amount back, minus their own share
        payer_id = expense.payer_id
        balances.setdefault(payer_id, 0.0)
        
        if share_per_person == 0:
            balances[payer_id] += total_amount
        else:
            # Payer is owed (Total - their personal share)
            balances[payer_id] += (total_amount - share_per_person)

        # 2. Update Participants' Balances
        # Each participant owes their share
        for participant in participants:
            # Use participant.id (SQLAlchemy model) or ID directly
            participant_id = participant.id if hasattr(participant, 'id') else participant
            
            # Skip if participant is also the payer (payer's share handled above)
            if participant_id == payer_id:
                continue
                
            balances.setdefault(participant_id, 0.0)
            balances[participant_id] -= share_per_person
            
    return balances


def compute_settlements(balances):
    """
    Convert net balances into a list of specific 'who pays whom' transactions.
    This uses a simple greedy algorithm to minimize the number of payments.
    """
    creditors = [] # People people who are owed money (positive balance)
    debtors = []   # People who owe money (negative balance)

    for user_id, balance in balances.items():
        amount = round(balance, 2)
        if amount > 0:
            creditors.append([user_id, amount])
        elif amount < 0:
            debtors.append([user_id, -amount]) # Convert to positive for easier math

    # Sort to settle largest debts first
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    settlements = []
    debtor_idx = 0
    creditor_idx = 0

    # Match debtors with creditors until everything is settled
    while debtor_idx < len(debtors) and creditor_idx < len(creditors):
        debtor_id, amount_owed = debtors[debtor_idx]
        creditor_id, amount_due = creditors[creditor_idx]

        # The amount to transfer is the smaller of what's owed or what's due
        transfer_amount = min(amount_owed, amount_due)
        
        settlements.append({
            'from': debtor_id, 
            'to': creditor_id, 
            'amount': round(transfer_amount, 2)
        })

        # Update remaining amounts
        debtors[debtor_idx][1] -= transfer_amount
        creditors[creditor_idx][1] -= transfer_amount

        # Move to next person if their balance is now zero
        if debtors[debtor_idx][1] == 0:
            debtor_idx += 1
        if creditors[creditor_idx][1] == 0:
            creditor_idx += 1

    return settlements

# Expenses routes
@app.route('/trip/<int:trip_id>/expenses')
@login_required
def trip_expenses(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    # allow trip owner or participants — using owner check for now
    # TODO: extend to group members if trips can be shared
    if not is_trip_member(trip_id, current_user.id):
        abort(403)
    expenses = Expense.query.filter_by(trip_id=trip_id).order_by(Expense.id.desc()).all()
    # prepare participants display
    exp_list = []
    for e in expenses:
        exp_list.append({
            'id': e.id,
            'title': e.title,
            'amount': float(e.amount),
            'payer': e.payer.name if e.payer else 'Unknown',
            'participants': [u.name for u in e.participants],
            'notes': e.notes
        })
    balances = compute_balances(trip_id)
    # translate balances to readable form
    user_balances = []
    # get all users involved: trip owner + participants + payers
    user_ids = set()
    # Add balance keys (should be user IDs)
    for uid in balances.keys():
        user_ids.add(int(uid) if not isinstance(uid, int) else uid)
    # Add participants and payer IDs
    for e in expenses:
        user_ids.update([int(u.id) if hasattr(u, 'id') else int(u) for u in e.participants])
        user_ids.add(int(e.payer_id))
    # Ensure all are integers
    user_ids = {int(uid) for uid in user_ids}
    users = User.query.filter(User.id.in_(list(user_ids))).all() if user_ids else []
    user_map = {u.id: u for u in users}
    
    # Normalize balances dictionary keys to integers for lookup
    normalized_balances = {}
    for key, value in balances.items():
        normalized_key = int(key.id) if hasattr(key, 'id') else int(key)
        normalized_balances[normalized_key] = value
    
    for uid in user_ids:
        u = user_map.get(uid)
        balance = normalized_balances.get(uid, 0.0)
        user_balances.append({'user_id': uid, 'name': u.name if u else 'Unknown', 'balance': round(balance, 2)})
    # compute settlements (use normalized balances)
    settlements_raw = compute_settlements(normalized_balances)
    settlements = []
    for s in settlements_raw:
        from_id = int(s['from'])
        to_id = int(s['to'])
        settlements.append({
            'from': from_id, 
            'to': to_id, 
            'amount': s['amount'], 
            'from_name': user_map.get(from_id).name if user_map.get(from_id) else str(from_id), 
            'to_name': user_map.get(to_id).name if user_map.get(to_id) else str(to_id)
        })
    return render_template('trip_expenses.html', trip=trip, expenses=exp_list, balances=user_balances, settlements=settlements)


@app.route('/trip/<int:trip_id>/expenses/create', methods=['GET','POST'])
@login_required
def create_expense(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if not is_trip_member(trip_id, current_user.id):
        abort(403)
    form = ExpenseForm()
    # populate payer/participants choices from users involved in the trip: owner + group members
    users_q = [trip.owner]
    if getattr(trip, 'group_id', None):
        members = GroupMember.query.filter_by(group_id=trip.group_id).all()
        users_q = [trip.owner] + [m.user for m in members]
    # dedupe
    seen = set()
    choices = []
    for u in users_q:
        if u and u.id not in seen:
            seen.add(u.id)
            choices.append((u.id, f"{u.name} (id:{u.id})"))
    form.payer.choices = choices
    form.participants.choices = choices
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                title = form.title.data.strip()
                if not title:
                    flash('Title is required', 'danger')
                    return render_template('create_expense.html', trip=trip, form=form)
                
                # Parse amount
                try:
                    amount = float(form.amount.data)
                    if amount <= 0:
                        flash('Amount must be greater than 0', 'danger')
                        return render_template('create_expense.html', trip=trip, form=form)
                except (ValueError, TypeError):
                    flash('Invalid amount. Please enter a valid number.', 'danger')
                    return render_template('create_expense.html', trip=trip, form=form)
                
                payer_id = form.payer.data
                if not payer_id:
                    flash('Please select a payer', 'danger')
                    return render_template('create_expense.html', trip=trip, form=form)
                
                participant_ids = form.participants.data or []
                notes = (form.notes.data or '').strip()
                
                # Create expense
                exp = Expense(
                    trip_id=trip_id, 
                    title=title, 
                    amount=amount, 
                    payer_id=payer_id, 
                    notes=notes if notes else None
                )
                
                # Attach participants
                if participant_ids:
                    users = User.query.filter(User.id.in_(participant_ids)).all()
                    exp.participants = users
                
                db.session.add(exp)
                db.session.commit()
                
                flash(f'Expense "{title}" added successfully! ₹{amount:.2f}', 'success')
                return redirect(url_for('trip_expenses', trip_id=trip_id))
                
            except Exception as e:
                db.session.rollback()
                app.logger.exception("Error creating expense")
                flash(f'An error occurred while creating the expense: {str(e)}', 'danger')
                return render_template('create_expense.html', trip=trip, form=form)
        else:
            # Form validation failed - show errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    
    return render_template('create_expense.html', trip=trip, form=form)


@app.route('/expenses/<int:expense_id>/edit', methods=['GET','POST'])
@login_required
def edit_expense(expense_id):
    exp = Expense.query.get_or_404(expense_id)
    if not is_trip_member(exp.trip_id, current_user.id):
        abort(403)
    form = ExpenseForm()
    # populate payer/participants choices like in create
    trip = exp.trip
    users_q = [trip.owner]
    if getattr(trip, 'group_id', None):
        members = GroupMember.query.filter_by(group_id=trip.group_id).all()
        users_q = [trip.owner] + [m.user for m in members]
    seen = set()
    choices = []
    for u in users_q:
        if u and u.id not in seen:
            seen.add(u.id)
            choices.append((u.id, f"{u.name} (id:{u.id})"))
    form.payer.choices = choices
    form.participants.choices = choices
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                exp.title = form.title.data.strip()
                if not exp.title:
                    flash('Title is required', 'danger')
                    return render_template('create_expense.html', trip=exp.trip, form=form)
                
                try:
                    amount = float(form.amount.data)
                    if amount <= 0:
                        flash('Amount must be greater than 0', 'danger')
                        return render_template('create_expense.html', trip=exp.trip, form=form)
                    exp.amount = amount
                except (ValueError, TypeError):
                    flash('Invalid amount. Please enter a valid number.', 'danger')
                    return render_template('create_expense.html', trip=exp.trip, form=form)
                
                exp.payer_id = form.payer.data
                participant_ids = form.participants.data or []
                if participant_ids:
                    exp.participants = User.query.filter(User.id.in_(participant_ids)).all()
                else:
                    exp.participants = []
                exp.notes = (form.notes.data or '').strip() or None
                
                db.session.commit()
                flash(f'Expense updated successfully! ₹{exp.amount:.2f}', 'success')
                return redirect(url_for('trip_expenses', trip_id=exp.trip_id))
            except Exception as e:
                db.session.rollback()
                app.logger.exception("Error updating expense")
                flash(f'An error occurred while updating the expense: {str(e)}', 'danger')
        else:
            # Form validation failed - show errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    # populate form
    if request.method == 'GET':
        form.title.data = exp.title
        form.amount.data = str(float(exp.amount))
        form.payer.data = exp.payer_id
        form.participants.data = [u.id for u in exp.participants]
        form.notes.data = exp.notes
    return render_template('create_expense.html', trip=exp.trip, form=form)


@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    exp = Expense.query.get_or_404(expense_id)
    if not is_trip_member(exp.trip_id, current_user.id):
        abort(403)
    db.session.delete(exp)
    db.session.commit()
    flash('Expense deleted', 'info')
    return redirect(url_for('trip_expenses', trip_id=exp.trip_id))

# --- Routes ---
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        normalized_email = (form.email.data or '').strip().lower()
        if User.query.filter_by(email=normalized_email).first():
            flash('Email already registered', 'warning')
            return render_template('register.html', form=form)

        user = User(name=form.name.data, email=normalized_email)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Registration successful!", "success")
        
        # Check for 'next' parameter to redirect back to join link
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
            
        return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # normalize email lookup to lowercase so stored lowercase addresses match
        email_lookup = (form.email.data or '').strip().lower()
        user = User.query.filter_by(email=email_lookup).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash("Login successful!", "success")
            
            # Check for 'next' parameter
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
                
            return redirect(url_for('dashboard'))
        flash("Invalid email or password.", "danger")
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('home'))


# --- Dashboard & Trip CRUD ---
@app.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    
    # Get trips owned by the user
    owned_trips = Trip.query.filter_by(user_id=current_user.id).all()
    
    # Get trips from groups the user is a member of
    user_group_ids = [gm.group_id for gm in GroupMember.query.filter_by(user_id=current_user.id).all()]
    group_trips = []
    if user_group_ids:
        group_trips = Trip.query.filter(
            Trip.group_id.in_(user_group_ids),
            Trip.user_id != current_user.id  # Exclude trips already owned by user
        ).all()
    
    # Combine all trips and remove duplicates
    all_trips = list(set(owned_trips + group_trips))
    
    # Sort by start date
    all_trips.sort(key=lambda t: t.start_date)
    
    # Categorize trips
    upcoming = [t for t in all_trips if t.start_date > today]
    ongoing = [t for t in all_trips if t.start_date <= today <= t.end_date]
    completed = [t for t in all_trips if t.end_date < today]
    
    # Get user's groups through GroupMember association
    my_groups = (Group.query
                .join(GroupMember)
                .filter(GroupMember.user_id == current_user.id)
                .order_by(Group.name)
                .all())
    
    # Add member count to each group
    for group in my_groups:
        group.member_count = GroupMember.query.filter_by(group_id=group.id).count()
        group.is_member = True  # Flag to indicate user is a member
    
    return render_template('dashboard.html', 
                         upcoming=upcoming, 
                         ongoing=ongoing, 
                         completed=completed,
                         my_groups=my_groups)


@app.route('/create_trip', methods=['GET', 'POST'])
@login_required
def create_trip():
    form = TripForm()
    
    # Populate group choices with user's groups (where they are admin or member)
    user_groups = (Group.query
                   .join(GroupMember)
                   .filter(GroupMember.user_id == current_user.id)
                   .filter(Group.is_active == True)
                   .all())
    admin_groups = Group.query.filter_by(admin_id=current_user.id, is_active=True).all()
    all_user_groups = list(set(user_groups + admin_groups))
    form.group_id.choices = [(0, 'No Group')] + [(g.id, g.name) for g in all_user_groups]
    
    if form.validate_on_submit():
        cover_image_path = None
        file_path = None
        
        try:
            # Handle cover image if provided
            if form.cover_image.data:
                file = form.cover_image.data
                if file.filename:
                    # Validate file type
                    ext = os.path.splitext(file.filename)[1].lower()
                    if ext not in ['.jpg', '.jpeg', '.png']:
                        flash('Please upload only JPG or PNG images', 'danger')
                        return render_template('create_trip.html', form=form)
                    
                    # Generate safe filename and save
                    filename = secure_filename(f"{uuid.uuid4()}{ext}")
                    # ensure folder exists right before saving (safer in concurrent runs)
                    try:
                        os.makedirs(app.config['TRIP_COVERS_FOLDER'], exist_ok=True)
                    except Exception as makedir_err:
                        app.logger.error(f"Failed to ensure cover folder exists: {makedir_err}")
                    file_path = os.path.join(app.config['TRIP_COVERS_FOLDER'], filename)
                    try:
                        file.save(file_path)
                        cover_image_path = f"uploads/trip_covers/{filename}"
                        app.logger.info(f"Saved cover image: {filename}")
                    except Exception as save_error:
                        app.logger.exception("Error saving image")
                        flash('Failed to save the image. Please try again.', 'danger')
                        return render_template('create_trip.html', form=form)
            
            # Create trip
            group_id = form.group_id.data if form.group_id.data and form.group_id.data != 0 else None
            trip = Trip(
                user_id=current_user.id,
                group_id=group_id,
                title=form.title.data,
                destination=form.destination.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                description=form.description.data,
                cover_image=cover_image_path
            )
            
            db.session.add(trip)
            db.session.commit()
            
            if cover_image_path:
                flash('✅ Trip created successfully with cover image! 🌄', 'success')
            else:
                flash('✅ Trip created successfully!', 'success')
            return redirect(url_for('dashboard'))
        
        except Exception as e:
            db.session.rollback()
            # Clean up uploaded file if DB save failed
            if cover_image_path and file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to clean up image: {cleanup_error}")
            # log full exception with traceback
            app.logger.exception("Error creating trip")
            # provide a slightly more detailed error to the UI to help debugging (but avoid leaking internals)
            flash(f'An error occurred while creating the trip: {type(e).__name__}: {str(e)}', 'danger')
            return render_template('create_trip.html', form=form)
    
    # If there are validation errors, show them as flashes so the user can correct inputs
    if form.errors:
        for field, errs in form.errors.items():
            flash(f"{field}: {', '.join(errs)}", 'danger')

    # pass today's date to template for client-side min enforcement
    return render_template('create_trip.html', form=form, today_str=date.today().isoformat())


@app.route('/view_trip/<int:trip_id>')
@login_required
def view_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    # allow owner or trip members to view
    if not is_trip_member(trip_id, current_user.id):
        abort(403)
    # show itinerary items grouped by date for the trip
    items = ItineraryItem.query.filter_by(trip_id=trip.id).order_by(ItineraryItem.datetime).all()
    # build a list of dates present
    from collections import defaultdict
    grouped = defaultdict(list)
    for it in items:
        grouped[it.datetime.date()].append(it)

    sorted_dates = sorted(grouped.keys())
    
    # Get group info if trip is associated with a group
    group = None
    if trip.group_id:
        group = Group.query.get(trip.group_id)
    
    return render_template('view_trip.html', 
                         trip=trip, 
                         itinerary_items=items, 
                         grouped_itinerary=grouped, 
                         itinerary_dates=sorted_dates,
                         group=group)


@app.route('/trip/<int:trip_id>/itinerary/create', methods=['GET', 'POST'])
@login_required
def create_itinerary(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    # allow trip owner or participants
    if not is_trip_member(trip_id, current_user.id):
        abort(403)
    form = ItineraryForm()
    form.trip = trip  # Pass trip to form for date validation
    if form.validate_on_submit():
        from datetime import datetime
        # Parse the time string (format: HH:MM), default to 00:00 if not provided
        time_str = form.time.data if form.time.data else '00:00'
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        # Combine date and time
        dt = datetime.combine(form.date.data, time_obj)
        
        item = ItineraryItem(
            trip_id=trip.id,
            title=form.title.data,
            description=form.description.data,
            datetime=dt,
            location=form.location.data,
            cost=(float(form.cost.data) if form.cost.data else None),
            tags=form.tags.data,
        )
        db.session.add(item)
        db.session.commit()
        flash('Itinerary item added', 'success')
        return redirect(url_for('view_trip', trip_id=trip.id))
    return render_template('create_itinerary.html', form=form, trip=trip)


@app.route('/itinerary/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_itinerary(item_id):
    item = ItineraryItem.query.get_or_404(item_id)
    trip = item.trip
    if trip.user_id != current_user.id:
        abort(403)
    form = ItineraryForm(obj=item)
    form.trip = trip  # Pass trip to form for date validation
    if form.validate_on_submit():
        from datetime import datetime
        # Parse the time string (format: HH:MM), default to 00:00 if not provided
        time_str = form.time.data if form.time.data else '00:00'
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        # Combine date and time
        item.title = form.title.data
        item.description = form.description.data
        item.datetime = datetime.combine(form.date.data, time_obj)
        item.location = form.location.data
        item.cost = (float(form.cost.data) if form.cost.data else None)
        item.tags = form.tags.data
        db.session.commit()
        flash('Itinerary updated', 'success')
        return redirect(url_for('view_trip', trip_id=trip.id))
    return render_template('edit_itinerary.html', form=form, trip=trip, item=item)


@app.route('/itinerary/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_itinerary(item_id):
    item = ItineraryItem.query.get_or_404(item_id)
    trip = item.trip
    if trip.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash('Itinerary item deleted', 'info')
    return redirect(url_for('view_trip', trip_id=trip.id))


@app.route('/edit_trip/<int:trip_id>', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    # only owner can edit their own trip
    if trip.user_id != current_user.id:
        abort(403)

    form = TripForm(obj=trip)
    
    # Populate group choices with user's groups (where they are admin or member)
    user_groups = (Group.query
                   .join(GroupMember)
                   .filter(GroupMember.user_id == current_user.id)
                   .filter(Group.is_active == True)
                   .all())
    admin_groups = Group.query.filter_by(admin_id=current_user.id, is_active=True).all()
    all_user_groups = list(set(user_groups + admin_groups))
    form.group_id.choices = [(0, 'No Group')] + [(g.id, g.name) for g in all_user_groups]
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                # Update trip details
                trip.title = form.title.data
                trip.destination = form.destination.data
                trip.start_date = form.start_date.data
                trip.end_date = form.end_date.data
                trip.description = form.description.data
                trip.group_id = form.group_id.data if form.group_id.data and form.group_id.data != 0 else None
                
                # Save changes
                db.session.commit()
                flash('Trip updated successfully', 'success')
                return redirect(url_for('view_trip', trip_id=trip.id))
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error updating trip: {str(e)}")
                flash('An error occurred while updating the trip', 'danger')
        else:
            # If form validation failed, show errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{getattr(form, field).label.text}: {error}", 'danger')

    # Pre-populate form for GET request or if validation failed
    if request.method == 'GET':
        form.group_id.data = trip.group_id if trip.group_id else 0
    return render_template('edit_trip.html', form=form, trip=trip)


@app.route('/delete_trip/<int:trip_id>', methods=['POST'])
@login_required
def delete_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    # only owner can delete their own trip
    if trip.user_id != current_user.id:
        abort(403)
        
    try:
        # First delete all related itinerary items
        # Use session-level bulk delete to avoid session synchronization issues
        db.session.query(ItineraryItem).filter_by(trip_id=trip_id).delete(synchronize_session=False)
        # Also delete expenses related to this trip (and their participant links via cascade/association)
        db.session.query(Expense).filter_by(trip_id=trip_id).delete(synchronize_session=False)
        
        # Now delete the trip
        db.session.delete(trip)
        
        # Clean up cover image if it exists. cover_image is stored relative to static,
        # e.g. 'uploads/trip_covers/<filename>' so build absolute path from app.root_path
        if trip.cover_image:
            try:
                file_path = os.path.join(app.root_path, 'static', trip.cover_image)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    app.logger.info(f"Removed cover image file: {file_path}")
            except Exception:
                app.logger.exception("Failed to delete cover image")
        
        db.session.commit()
        flash('Trip and all related items deleted successfully', 'info')
        
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Error deleting trip")
        flash(f'An error occurred while deleting the trip: {type(e).__name__}: {str(e)}', 'danger')
        
    return redirect(url_for('dashboard'))


@app.route('/groups')
@login_required
def groups():
    """Display groups page with user's groups and available groups."""
    # Get groups the user is a member of
    my_groups = (Group.query
                .join(GroupMember)
                .filter(GroupMember.user_id == current_user.id)
                .filter(Group.is_active == True)
                .order_by(Group.name)
                .all())

    # Get groups administered by the user
    admin_groups = Group.query.filter_by(admin_id=current_user.id, is_active=True).all()
    
    # Get all active groups
    all_groups = Group.query.filter_by(is_active=True).order_by(Group.name).all()
    
    # Generate QR codes for admin's groups
    for group in admin_groups:
        if not hasattr(group, 'qr_code'):
            import qrcode
            import base64
            from io import BytesIO
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(group.get_join_url())
            qr.make(fit=True)
            
            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64 for embedding in HTML
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            group.qr_code = base64.b64encode(buffer.getvalue()).decode()

    return render_template('groups.html',
                         my_groups=my_groups,
                         admin_groups=admin_groups,
                         all_groups=all_groups)

@app.route('/groups/join/<token>')
@app.route('/groups/<int:group_id>/join', methods=['POST'])
@login_required
def join_group(token=None, group_id=None):
    """Handle group joining via token/QR code or direct group ID."""
    try:
        if token:
            # Find the group with the given token
            group = Group.query.filter_by(join_token=token, is_active=True).first_or_404()
        elif group_id:
            # Find group by ID for direct joins
            group = Group.query.filter_by(id=group_id, is_active=True).first_or_404()
        else:
            flash('Invalid join request.', 'error')
            return redirect(url_for('groups'))
        
        # Check if user is already a member
        if group.is_member(current_user.id):
            flash('You are already a member of this group.', 'info')
            return redirect(url_for('group_detail', group_id=group.id))
        
        # Check if group is active
        if not group.is_active:
            flash('This group is no longer active.', 'warning')
            return redirect(url_for('groups'))
        
        # Add user as member with pending status if approval is required
        status = 'pending' if group.approval_required else 'active'
        member = GroupMember(
            group_id=group.id,
            user_id=current_user.id,
            role='member',
            status=status
        )
        db.session.add(member)
        
        if status == 'active':
            # Add a welcome message to the group chat only for active members
            welcome_msg = GroupMessage(
                group_id=group.id,
                user_id=current_user.id,
                message=f"👋 {current_user.name} joined the group!",
                timestamp=datetime.utcnow()
            )
            db.session.add(welcome_msg)
            
            # Emit socket event if SocketIO is enabled
            if SOCKETIO_ENABLED and socketio:
                socketio.emit('new_message', {
                    'user': current_user.name,
                    'user_id': current_user.id,
                    'text': f"👋 {current_user.name} joined the group!",
                    'timestamp': welcome_msg.timestamp.isoformat() + 'Z',
                    'is_status': True
                }, room=f'group_{group.id}')
            
            flash(f'Successfully joined the group: {group.name}!', 'success')
        else:
            flash(f'Your request to join "{group.name}" has been sent and is awaiting admin approval.', 'info')
        
        db.session.commit()
        return redirect(url_for('group_detail', group_id=group.id))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error joining group: {str(e)}')
        flash('An error occurred while joining the group.', 'danger')
        return redirect(url_for('groups'))

@app.route('/groups/<int:group_id>')
@login_required
def group_detail(group_id):
    """Display group details, members, and chat."""
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member or admin
    is_member = group.is_member(current_user.id)
    is_admin = group.admin_id == current_user.id
    
    if not is_member and not is_admin:
        # Check if they have a pending request
        pending = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id, status='pending').first()
        if pending:
            return render_template('group_pending.html', group=group)
            
        flash('You must be a member to view this group.', 'warning')
        return redirect(url_for('groups'))
    
    # Get active group members
    member_data = (db.session.query(User, GroupMember)
                  .join(GroupMember, User.id == GroupMember.user_id)
                  .filter(GroupMember.group_id == group_id)
                  .filter(GroupMember.status == 'active')
                  .order_by(GroupMember.joined_at)
                  .all())
    
    # Get pending requests for admin
    pending_requests = []
    if is_admin:
        pending_requests = (db.session.query(User, GroupMember)
                          .join(GroupMember, User.id == GroupMember.user_id)
                          .filter(GroupMember.group_id == group_id)
                          .filter(GroupMember.status == 'pending')
                          .all())
    
    # Format members data for template
    members = []
    for user, group_member in member_data:
        members.append({
            'user': user,
            'role': group_member.role,
            'joined_at': group_member.joined_at,
            'is_admin': group_member.role == 'admin' or user.id == group.admin_id
        })
    
    # Get recent messages (last 100, but in ascending order)
    messages = (GroupMessage.query
               .filter_by(group_id=group_id)
               .order_by(GroupMessage.timestamp.desc())
               .limit(100)
               .all())
    messages.reverse() # Show oldest to newest
    
    return render_template('group_detail.html',
                         group=group,
                         members=members,
                         pending_requests=pending_requests,
                         messages=messages,
                         is_member=is_member,
                         current_user_id=current_user.id)


@app.route('/groups/<int:group_id>/messages', methods=['POST'])
@login_required
def send_message(group_id):
    """Handle sending a new message in the group chat."""
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member
    if not group.is_member(current_user.id):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get message content
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
    
    message_text = data['message'].strip()
    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    try:
        # Create and save the message
        message = GroupMessage(
            group_id=group_id,
            user_id=current_user.id,
            message=message_text
        )
        db.session.add(message)
        db.session.commit()
        
        # Prepare response data for real-time update
        response = {
            'id': message.id,
            'user': current_user.name,
            'user_id': current_user.id,
            'text': message.message,
            'timestamp': message.timestamp.isoformat() + 'Z',
            'is_admin': group.admin_id == current_user.id
        }
        
        # If SocketIO is enabled, emit to room
        if SOCKETIO_ENABLED and socketio:
            socketio.emit('new_message', response, room=f'group_{group_id}')
        
        return jsonify(response)
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error sending message: {str(e)}')
        return jsonify({'error': 'Failed to send message'}), 500

@app.route('/groups/<int:group_id>/messages')
@login_required
def get_messages(group_id):
    """Get recent messages for a group."""
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member
    if not group.is_member(current_user.id):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get messages with user info (Fetch newest first to limit)
    messages = (db.session.query(GroupMessage, User)
               .join(User)
               .filter(GroupMessage.group_id == group_id)
               .order_by(GroupMessage.timestamp.desc())
               .limit(100)
               .all())
    
    # Explicitly sort to ensure oldest to newest
    messages = sorted(messages, key=lambda x: x[0].timestamp)
    
    response = [{
        'id': msg.id,
        'user': user.name,
        'text': msg.message,
        'timestamp': msg.timestamp.isoformat() + 'Z' if msg.timestamp else None,
        'is_admin': group.admin_id == user.id,
        'user_id': msg.user_id,
        'media_filename': msg.media_filename,
        'location_lat': msg.location_lat,
        'location_lng': msg.location_lng,
        'location_label': msg.location_label,
        'is_status': 'joined' in msg.message or 'left' in msg.message
    } for msg, user in messages]
    
    return jsonify(response)

@app.route('/trip/<int:trip_id>/share/<token>', methods=['GET'])
@login_required
def share_trip(trip_id, token):
    """Handle trip sharing - join the user to the group associated with the trip."""
    trip = Trip.query.get_or_404(trip_id)
    
    # Verify the share token
    if not trip.share_token or trip.share_token != token:
        flash('Invalid share link. The link may have expired or been modified.', 'danger')
        app.logger.warning(f'Invalid share token attempt: trip_id={trip_id}, token={token[:10]}...')
        return redirect(url_for('dashboard'))
    
    # Check if trip is associated with a group
    if not trip.group_id:
        flash('This trip is not associated with a group. Please contact the trip owner to link it to a group first.', 'warning')
        return redirect(url_for('view_trip', trip_id=trip_id))
    
    group = Group.query.get_or_404(trip.group_id)
    
    # Check if group is active
    if not group.is_active:
        flash('The group associated with this trip is no longer active.', 'warning')
        return redirect(url_for('view_trip', trip_id=trip_id))
    
    # Check if user is already a member
    if group.is_member(current_user.id):
        flash(f'You are already a member of the group "{group.name}".', 'info')
        return redirect(url_for('view_trip', trip_id=trip_id))
    
    try:
        # Add user as member
        member = GroupMember(
            group_id=group.id,
            user_id=current_user.id,
            role='member'
        )
        db.session.add(member)
        
        # Add a welcome message to the group chat
        welcome_msg = GroupMessage(
            group_id=group.id,
            user_id=current_user.id,
            message=f"👋 {current_user.name} joined via trip: {trip.title}!"
        )
        db.session.add(welcome_msg)
        
        db.session.commit()
        
        # Emit socket event if SocketIO is enabled
        if SOCKETIO_ENABLED and socketio:
            socketio.emit('member_joined', {
                'group_id': group.id,
                'user_name': current_user.name,
                'user_id': current_user.id
            }, room=f'group_{group.id}')
        
        flash(f'Successfully joined the group "{group.name}"! The trip "{trip.title}" is now available on your dashboard.', 'success')
        return redirect(url_for('view_trip', trip_id=trip_id))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error joining group via trip share: {str(e)}')
        flash('An error occurred while joining the group.', 'danger')
        return redirect(url_for('view_trip', trip_id=trip_id))


@app.route('/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    """Create a new group with join token and QR code."""
    form = GroupForm()
    if form.validate_on_submit():
        try:
            # Create new group
            group = Group(
                name=form.name.data,
                description=form.description.data,
                admin_id=current_user.id,
                is_active=True
            )
            # Generate unique join token
            group.generate_join_token()
            db.session.add(group)
            # Flush to ensure group.id is populated before creating the GroupMember
            db.session.flush()

            # Add creator as admin member (use the populated group.id)
            member = GroupMember(
                group_id=group.id,
                user_id=current_user.id,
                role='admin'
            )
            db.session.add(member)
            db.session.commit()
            
            flash('Group created successfully! Share the join link or QR code to invite members.', 'success')
            return redirect(url_for('group_detail', group_id=group.id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.exception('Error creating group')
            flash(f'An error occurred while creating the group: {type(e).__name__}: {str(e)}', 'danger')
    
    return render_template('create_group.html', form=form)


@app.route('/groups/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    grp = Group.query.get_or_404(group_id)
    gm = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    if not gm:
        flash('Not a member', 'warning')
        return redirect(url_for('group_detail', group_id=group_id))
    # prevent admin from leaving if they're the only admin
    if gm.role == 'admin':
        other_admin = GroupMember.query.filter(GroupMember.group_id==group_id, GroupMember.user_id!=current_user.id, GroupMember.role=='admin').first()
        if not other_admin:
            flash('Transfer admin role before leaving', 'warning')
            return redirect(url_for('group_detail', group_id=group_id))
    db.session.delete(gm)
    db.session.commit()
    flash('Left group', 'info')
    return redirect(url_for('groups'))


@app.route('/groups/<int:group_id>/remove/<int:user_id>', methods=['POST'])
@login_required
def remove_member(group_id, user_id):
    """Allow group admin to remove a member."""
    group = Group.query.get_or_404(group_id)
    
    # Only group admin can remove members
    if group.admin_id != current_user.id:
        flash('Only the group admin can remove members.', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))
        
    # Prevent admin from removing themselves
    if user_id == current_user.id:
        flash('You cannot remove yourself. Use Delete Group or Leave Group instead.', 'warning')
        return redirect(url_for('group_detail', group_id=group_id))
        
    member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first_or_404()
    
    try:
        user_name = member.user.name
        db.session.delete(member)
        db.session.commit()
        flash(f'Member "{user_name}" removed successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error removing member: {str(e)}")
        flash('An error occurred while removing the member.', 'danger')
        
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Delete a group. Only the admin can delete their group."""
    group = Group.query.get_or_404(group_id)
    
    # Check if user is the admin
    if group.admin_id != current_user.id:
        flash('Only the group admin can delete the group.', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))
    
    try:
        # Delete all related data (cascade will handle most of it)
        # Delete all messages
        GroupMessage.query.filter_by(group_id=group_id).delete()
        
        # Delete all members
        GroupMember.query.filter_by(group_id=group_id).delete()
        
        # Delete all trips associated with this group
        trips = Trip.query.filter_by(group_id=group_id).all()
        for trip in trips:
            # Delete trip expenses
            Expense.query.filter_by(trip_id=trip.id).delete()
            # Delete itinerary items
            ItineraryItem.query.filter_by(trip_id=trip.id).delete()
            # Delete trip cover image if exists
            if trip.cover_image:
                try:
                    file_path = os.path.join(app.root_path, 'static', trip.cover_image)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    app.logger.exception("Failed to delete trip cover image")
            # Delete the trip
            db.session.delete(trip)
        
        # Delete the group
        db.session.delete(group)
        db.session.commit()
        
        flash('Group deleted successfully', 'success')
        return redirect(url_for('groups'))
        
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Error deleting group")
        flash(f'An error occurred while deleting the group: {type(e).__name__}: {str(e)}', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/groups/<int:group_id>/reset_link', methods=['POST'])
@login_required
def reset_group_link(group_id):
    """Regenerate the group join token."""
    group = Group.query.get_or_404(group_id)
    if group.admin_id != current_user.id:
        flash('Only admins can reset the invite link.', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))
        
    group.generate_join_token()
    db.session.commit()
    flash('Invitation link has been reset. Old links will no longer work.', 'success')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/toggle_approval', methods=['POST'])
@login_required
def toggle_group_approval(group_id):
    """Toggle whether join requests require admin approval."""
    group = Group.query.get_or_404(group_id)
    if group.admin_id != current_user.id:
        flash('Only admins can change security settings.', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))
        
    group.approval_required = not group.approval_required
    db.session.commit()
    status = "enabled" if group.approval_required else "disabled"
    flash(f'Join approvals have been {status}.', 'info')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_join_request(group_id, user_id):
    """Approve a pending join request."""
    group = Group.query.get_or_404(group_id)
    if group.admin_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))
        
    member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id, status='pending').first_or_404()
    member.status = 'active'
    
    # Add welcome message
    welcome_msg = GroupMessage(
        group_id=group.id,
        user_id=user_id,
        message=f"👋 {member.user.name} joined the group!",
        timestamp=datetime.utcnow()
    )
    db.session.add(welcome_msg)
    db.session.commit()

    # Emit to room if SocketIO active
    if SOCKETIO_ENABLED and socketio:
        socketio.emit('new_message', {
            'user': member.user.name,
            'user_id': user_id,
            'text': f"👋 {member.user.name} joined the group!",
            'timestamp': welcome_msg.timestamp.isoformat() + 'Z',
            'is_status': True
        }, room=f'group_{group_id}')

    flash(f'Approved {member.user.name}.', 'success')
    return redirect(url_for('group_detail', group_id=group_id))


@app.route('/groups/<int:group_id>/reject/<int:user_id>', methods=['POST'])
@login_required
def reject_join_request(group_id, user_id):
    """Reject/Delete a pending join request."""
    group = Group.query.get_or_404(group_id)
    if group.admin_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('group_detail', group_id=group_id))
        
    member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id, status='pending').first_or_404()
    user_name = member.user.name
    db.session.delete(member)
    db.session.commit()
    flash(f'Rejected request from {user_name}.', 'info')
    return redirect(url_for('group_detail', group_id=group_id))


# --- Run server ---
if __name__ == '__main__':
    import socket
    
    def find_free_port(start_port=5000, max_attempts=10):
        """Find a free port starting from start_port."""
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return port
            except OSError:
                continue
        return None
    
    # Get port from environment variable or use default
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    
    # Check if port is available
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
    except OSError:
        # Port is in use, try to find a free one
        print(f"⚠️  Port {port} is already in use. Searching for an available port...")
        free_port = find_free_port(port)
        if free_port:
            port = free_port
            print(f"✅ Using port {port} instead.")
        else:
            print(f"❌ Could not find an available port. Please stop the process using port {port} or set FLASK_RUN_PORT environment variable.")
            exit(1)
    
    if SOCKETIO_ENABLED and socketio is not None:
        # when SocketIO is available use its runner
        socketio.run(app, debug=True, port=port, host='127.0.0.1')
    else:
        app.run(debug=True, port=port, host='127.0.0.1')
