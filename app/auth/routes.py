"""Routes for authentication."""

import secrets
from urllib.parse import urlencode

import requests
from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth import auth_bp, forms
from app.constant import (
    AUTHORIZATION_CODE,
    AUTHORIZE_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    OAUTH2_PROVIDERS,
    OAUTH2_STATE,
    RESPONSE_TYPE,
    SCOPES,
    TOKEN_URL,
    FlashAlertTypeEnum,
    OAuthProviderEnum,
)
from app.extensions import db, login_manager
from app.models.user import User


@login_manager.user_loader
def user_loader(user_id: str):
    """Given *user_id*, return the associated User object."""
    return db.session.get(User, user_id)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user."""
    if current_user.is_authenticated:
        flash("You are already registered.", FlashAlertTypeEnum.SUCCESS.value)
        return redirect(url_for("auth.login"))

    form = forms.RegisterForm(request.form)

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user:
            flash("Email already registered.", FlashAlertTypeEnum.DANGER.value)
            return redirect(url_for("auth.register"))

        if form.password.data != form.confirm.data:
            flash("Passwords must match.", FlashAlertTypeEnum.DANGER.value)
            return redirect(url_for("auth.resgister"))

        # Create a new user
        user = User(
            username=form.username.data,
            email=form.email.data,
            avatar_url="",
            use_google=False,
            use_github=False,
            security_question=form.security_question.data,
            security_answer=form.security_answer.data,
        )
        user.password = form.password.data
        db.session.add(user)
        db.session.commit()

        login_user(user, remember=True)
        flash("You registered and are now logged in.", FlashAlertTypeEnum.SUCCESS.value)
        return redirect(url_for("index"))

    return render_template("register.html", form=form)


@auth_bp.route("/v1/check_email_exists/<email>")
def check_email_exists(email: str):
    """Check if the email exists."""
    print("check email:", email)
    user = User.query.filter_by(email=email).first()

    if user is not None:
        return {"message": "Email exists."}

    return {"message": "Email not exists."}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Log in the user."""
    form = forms.LoginForm(request.form)

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user is None:
            flash(
                "No user with that email exists, please register first.",
                FlashAlertTypeEnum.DANGER.value,
            )
            return redirect(url_for("auth.register"))

        if not user.password_hash:
            provide = "Google" if user.use_google else "GitHub"
            flash(f"Please login with {provide}.", FlashAlertTypeEnum.WARNING.value)
            return redirect(url_for("auth.login"))

        if not user.verify_password(form.password.data):
            flash(
                "Invalid email or password. Please try a different login method or attempt again.",
                FlashAlertTypeEnum.DANGER.value,
            )
            return redirect(url_for("auth.login"))

        login_user(user, remember=True)
        flash("You have been logged in.", FlashAlertTypeEnum.SUCCESS.value)
        return redirect(url_for("index"))

    return render_template("login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    """Log out the user."""
    logout_user()
    flash("You have been logged out.", FlashAlertTypeEnum.SUCCESS.value)
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """Render the forgoet password page."""
    form = forms.ForgotPasswordForm(request.form)

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user is None:
            flash("No user with that email exists.", FlashAlertTypeEnum.DANGER.value)
            return redirect(url_for("auth.forgot_password"))

        if user.security_answer != form.security_answer.data:
            flash("Invalid security answer.", FlashAlertTypeEnum.DANGER.value)
            return redirect(url_for("auth.forgot_password"))

        user.password = form.password.data
        db.session.commit()

        flash("Password has been reset.", FlashAlertTypeEnum.SUCCESS.value)
        return redirect(url_for("auth.login"))

    return render_template("forgotPassword.html", form=form)


@auth_bp.route("/v1/query_forgot_password_user/<email>")
def query_forgot_password_user(email: str):
    """Query the user for forgot password."""
    user = User.query.filter_by(email=email).first()

    if user is None:
        return {"message": "User not found"}

    return {"message": "User found", "user": user}


@auth_bp.route("/v1/authorize/<provider>")
def authorize(provider: str):
    """Redirect to provider's OAuth2 login page."""
    if not current_user.is_anonymous:
        return redirect(url_for("index"))

    provider_data = current_app.config[OAUTH2_PROVIDERS].get(provider)
    if provider_data is None:
        abort(404)

    session[OAUTH2_STATE] = secrets.token_urlsafe(16)

    qs = urlencode(
        {
            "client_id": provider_data[CLIENT_ID],
            "redirect_uri": url_for("auth.callback", provider=provider, _external=True),
            "response_type": RESPONSE_TYPE,
            "scope": " ".join(provider_data[SCOPES]),
            "state": session[OAUTH2_STATE],
        }
    )
    return redirect(provider_data[AUTHORIZE_URL] + "?" + qs)


@auth_bp.route("/v1/callback/<provider>")
def callback(provider: str):
    """Receive authorization code from provider and get user info."""
    if not current_user.is_anonymous:
        return redirect(url_for("index"))

    provider_data = current_app.config[OAUTH2_PROVIDERS].get(provider)
    if provider_data is None:
        abort(404)

    # get token from provider
    response = requests.post(
        provider_data[TOKEN_URL],
        data={
            "client_id": provider_data[CLIENT_ID],
            "client_secret": provider_data[CLIENT_SECRET],
            "code": request.args[RESPONSE_TYPE],
            "grant_type": AUTHORIZATION_CODE,
            "redirect_uri": url_for("auth.callback", provider=provider, _external=True),
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )

    if response.status_code != 200:
        abort(401)

    oauth2_token = response.json().get("access_token")
    if not oauth2_token:
        abort(401)

    # get user info from provider
    response = requests.get(
        provider_data["userinfo"]["url"],
        headers={
            "Authorization": "Bearer " + oauth2_token,
            "Accept": "application/json",
        },
        timeout=30,
    )
    user_info = response.json()

    if provider == OAuthProviderEnum.GOOGLE.value:
        username = user_info.get("name")
        email = user_info.get("email")
        avatar = user_info.get("picture")
    elif provider == OAuthProviderEnum.GITHUB.value:
        username = user_info.get("login")
        email = user_info.get("email")
        avatar = user_info.get("avatar_url")

    user = db.session.scalar(db.select(User).where(User.email == email))

    if user is None:
        user = User(
            username=username,
            email=email,
            avatar_url=avatar,
            use_google=provider == OAuthProviderEnum.GOOGLE.value,
            use_github=provider == OAuthProviderEnum.GITHUB.value,
        )
        db.session.add(user)
        db.session.commit()
    else:
        if not user.use_google and provider == OAuthProviderEnum.GOOGLE.value:
            user.use_google = True
        if not user.use_github and provider == OAuthProviderEnum.GITHUB.value:
            user.use_github = True
        user.username = username
        user.avatar_url = avatar
        db.session.commit()

    login_user(user, remember=True)
    flash("You have been logged in.", FlashAlertTypeEnum.SUCCESS.value)
    return redirect(url_for("index"))
