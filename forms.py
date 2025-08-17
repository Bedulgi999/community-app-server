
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, FileField
from wtforms.validators import DataRequired, Email, Length, EqualTo

class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=32)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=64)])
    password2 = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])

class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Body", validators=[DataRequired(), Length(max=10000)])
    image = FileField("Image")

class CommentForm(FlaskForm):
    body = StringField("Add a comment", validators=[DataRequired(), Length(max=1000)])

class ProfileForm(FlaskForm):
    bio = TextAreaField("Bio", validators=[Length(max=1000)])
    avatar = FileField("Avatar")
