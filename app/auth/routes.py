"""Routes for authentication."""

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_csrf_token,
    get_current_user,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
    verify_jwt_in_request,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf

from app.auth import auth_bp, forms
from app.constants import (
    AUTHORIZATION_CODE,
    AUTHORIZE_URL,
    CALLBACK_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    OAUTH2_PROVIDERS,
    OAUTH2_STATE,
    RESPONSE_TYPE,
    SCOPES,
    TOKEN_URL,
    FlashAlertTypeEnum,
    HttpRequestEnum,
    OAuthProviderEnum,
)
from app.extensions import db, login_manager
from app.models.user import User
from app.models.user_preference import UserPreference
from app.notice.events import NoticeTypeEnum, notice_event


@login_manager.user_loader
def user_loader(user_id: str):
    """Given *user_id*, return the associated User object."""

    return db.session.get(User, user_id)


@auth_bp.route("/auth", methods=["GET"])
def auth():
    """verification page."""

    form = forms.RegisterForm()
    return render_template("auth.html", form=form)


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user."""

    if current_user.is_authenticated:
        current_app.logger.info(
            "User is already registered, id: %s.", {current_user.id}
        )
        flash("You are already registered.", FlashAlertTypeEnum.SUCCESS.value)
        return redirect(url_for("auth.auth"))

    form = forms.RegisterForm(request.form)

    if form.validate_on_submit():

        user = User.query.filter_by(email=form.email.data).first()

        if user:
            if user.password_hash:
                # registered with email and password before
                current_app.logger.error(
                    "Email already registered, email: %s.", {form.email.data}
                )
                flash("Email already registered.", FlashAlertTypeEnum.DANGER.value)
                return redirect(url_for("auth.auth"))

            # only login with third party OAuth before
            user.username = form.username.data
            user.email = form.email.data
            user.avatar_url = (
                form.avatar_url.data if form.avatar_url.data else user.avatar_url
            )
            user.security_question = form.security_question.data
            user.security_answer = form.security_answer.data
            user.password = form.password.data

        else:

            # add a new user
            user = User(
                username=form.username.data,
                email=form.email.data,
                avatar_url=form.avatar_url.data,
                use_google=False,
                use_github=False,
                security_question=form.security_question.data,
                security_answer=form.security_answer.data,
            )
            user.password = form.password.data
            db.session.add(user)

        db.session.commit()
        login_user(user, remember=True)
        current_app.logger.info(
            "User registered, register email: %s, id: %s.", {user.email}, {user.id}
        )
        flash("You registered and are now logged in.", FlashAlertTypeEnum.SUCCESS.value)
        return redirect(url_for("auth.auth"))

    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                current_app.logger.error(
                    "Register error in field %s: %s",
                    {getattr(form, field).label.text},
                    {error},
                )
                flash(
                    f"{getattr(form, field).label.text}, {error}",
                    FlashAlertTypeEnum.DANGER.value,
                )

        return redirect(url_for("auth.auth"))

    abort(HttpRequestEnum.METHOD_NOT_ALLOWED.value)


@auth_bp.route("/login", methods=["POST"])
def login():
    """user login."""

    form = forms.LoginForm(request.form)
    if form.validate_on_submit():
        email = form.email.data
        user = User.query.filter_by(email=email).first()

        if user is None:
            current_app.logger.error("No user with that email exists: %s.", {email})
            flash(
                "No user with that email exists, please register first.",
                FlashAlertTypeEnum.DANGER.value,
            )
            return redirect(url_for("auth.auth"))

        if not user.password_hash:
            provide = "Google" if user.use_google else "GitHub"
            current_app.logger.error(
                "Please login with %s, email: %s.", {provide}, {email}
            )
            flash(f"Please login with {provide}.", FlashAlertTypeEnum.WARNING.value)
            return redirect(url_for("auth.auth"))

        if not user.verify_password(form.password.data):
            current_app.logger.error("Invalid email or password, email: %s.", {email})
            flash(
                "Invalid email or password. Please try a different login method or attempt again.",
                FlashAlertTypeEnum.DANGER.value,
            )
            return redirect(url_for("auth.auth"))

        # Log in the user with Flask-Login
        login_user(user, remember=True)
        current_app.logger.info("User logged in, id: %s.", {user.id})

        try:
            # Create JWT tokens with proper expiration
            access_token = create_access_token(
                identity=user.id,
                expires_delta=timedelta(minutes=15),  # 15 minutes expiration
            )
            refresh_token = create_refresh_token(
                identity=user.id, expires_delta=timedelta(days=30)  # 30 days expiration
            )

            # Create response
            response = redirect(url_for("index"))

            # Set JWT cookies with secure flags
            set_access_cookies(response, access_token)
            set_refresh_cookies(response, refresh_token)
            current_app.logger.info("JWT tokens created for user, id: %s", {user.id})

            # Set CSRF token with secure flags
            csrf_token = generate_csrf()
            response.set_cookie(
                "csrf_token", csrf_token, httponly=True, secure=True, samesite="Strict"
            )
            current_app.logger.info("CSRF token created for user, id: %s.", {user.id})

            flash("You have been logged in.", FlashAlertTypeEnum.SUCCESS.value)
            return response

        except Exception as e:
            current_app.logger.error(
                "Error creating tokens for user %s: %s", {user.id}, {str(e)}
            )
            flash(
                "Error during login process. Please try again.",
                FlashAlertTypeEnum.DANGER.value,
            )
            return redirect(url_for("auth.auth"))

    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                current_app.logger.error(
                    "Login error in field %s: %s",
                    {getattr(form, field).label.text},
                    {error},
                )
                flash(
                    f"{getattr(form, field).label.text}, {error}",
                    FlashAlertTypeEnum.DANGER.value,
                )
        return redirect(url_for("auth.auth"))

    abort(HttpRequestEnum.METHOD_NOT_ALLOWED.value)


@auth_bp.route("/logout", methods=["GET"])
@login_required
def logout():
    """Log out the user."""

    current_app.logger.info("User logged out, id: %s.", {current_user.id})
    logout_user()

    # jwt token
    response = redirect(url_for("auth.auth"))
    unset_jwt_cookies(response)

    flash("You have been logged out.", FlashAlertTypeEnum.SUCCESS.value)

    return response


@auth_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """Render the forgot password page."""

    form = forms.ForgotPasswordForm(request.form)

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user is None:
            current_app.logger.error(
                "No user with that email exists, email: %s.", {form.email.data}
            )
            flash("No user with that email exists.", FlashAlertTypeEnum.DANGER.value)
            return redirect(url_for("auth.forgot_password"))

        if user.security_answer != form.security_answer.data:
            current_app.logger.error(
                "Invalid security answer, email: %s, security answer: %s.",
                {form.email.data},
                {form.security_answer.data},
            )
            flash("Invalid security answer.", FlashAlertTypeEnum.DANGER.value)
            return redirect(url_for("auth.forgot_password"))

        user.password = form.password.data

        # update user password
        db.session.commit()
        current_app.logger.info(
            "User password updated, email: %s, id: %s.", {user.email}, {user.id}
        )

        # send notification
        notice_event(notice_type=NoticeTypeEnum.USER_RESET_PASSWORD)

        current_app.logger.info("Password reset for user, id: %s.", {user.id})
        flash("Password has been reset.", FlashAlertTypeEnum.SUCCESS.value)

        return redirect(url_for("auth.auth"))

    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                current_app.logger.error(
                    "Forgot password error in field %s: %s",
                    {getattr(form, field).label.text},
                    {error},
                )
                flash(
                    f"{getattr(form, field).label.text}, {error}",
                    FlashAlertTypeEnum.DANGER.value,
                )
        return redirect(url_for("auth.forgot_password"))

    return render_template("forgotPassword.html", form=form)


@auth_bp.route("/authorize/<provider>", methods=["GET"])
def authorize(provider: str):
    """Redirect to provider's OAuth2 login page."""

    if not current_user.is_anonymous:
        current_app.logger.info("User is already logged in, id: %s.", {current_user.id})
        return redirect(url_for("index"))

    provider_data = current_app.config[OAUTH2_PROVIDERS].get(provider)
    if provider_data is None:
        current_app.logger.error("Provider not found: %s.", {provider})
        abort(404)

    session[OAUTH2_STATE] = secrets.token_urlsafe(16)

    qs = urlencode(
        {
            "client_id": provider_data[CLIENT_ID],
            "redirect_uri": provider_data[CALLBACK_URL],
            "response_type": RESPONSE_TYPE,
            "scope": " ".join(provider_data[SCOPES]),
            "state": session[OAUTH2_STATE],
        }
    )
    return redirect(provider_data[AUTHORIZE_URL] + "?" + qs)


@auth_bp.route("/callback/<provider>", methods=["GET"])
def callback(provider: str):
    """Receive authorization code from provider and get user info."""

    provider_data = current_app.config[OAUTH2_PROVIDERS].get(provider)

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
        current_app.logger.error(
            "Failed to get token from provider: %s, status code: %s.",
            {provider},
            {response.status_code},
        )
        abort(401)

    oauth2_token = response.json().get("access_token")
    if not oauth2_token:
        current_app.logger.error("Failed to get token from provider: %s.", {provider})
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

    username = None
    email = None
    avatar = None

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
        # add a new user
        user = User(
            username=username,
            email=email,
            avatar_url=avatar,
            use_google=provider == OAuthProviderEnum.GOOGLE.value,
            use_github=provider == OAuthProviderEnum.GITHUB.value,
            security_question="",
            security_answer="",
        )
        db.session.add(user)

        # add user preference
        user_preference = UserPreference(user_id=user.id)
        db.session.add(user_preference)

    else:
        if not user.use_google and provider == OAuthProviderEnum.GOOGLE.value:
            user.use_google = True
        if not user.use_github and provider == OAuthProviderEnum.GITHUB.value:
            user.use_github = True
        if not user.avatar_url and avatar:
            user.avatar_url = avatar
        if not user.username and username:
            user.username = username
        if not user.email and email:
            user.email = email

    db.session.commit()

    try:
        # Log in the user with Flask-Login
        login_user(user, remember=True)
        current_app.logger.info(
            "User logged in with %s, id: %s.", {provider}, {current_user.id}
        )

        # Create JWT tokens with proper expiration
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(minutes=15),  # 15 minutes expiration
        )
        refresh_token = create_refresh_token(
            identity=user.id, expires_delta=timedelta(days=30)  # 30 days expiration
        )

        # Create response
        response = redirect(url_for("index"))

        # Set JWT cookies with secure flags
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        current_app.logger.info("JWT tokens created for user, id: %s", {user.id})

        # Set CSRF token with secure flags
        csrf_token = generate_csrf()
        response.set_cookie(
            "csrf_token", csrf_token, httponly=True, secure=True, samesite="Strict"
        )
        current_app.logger.info("CSRF token created for user, id: %s.", {user.id})

        flash("You have been logged in.", FlashAlertTypeEnum.SUCCESS.value)
        return response

    except Exception as e:
        current_app.logger.error(
            "Error during OAuth login for user %s: %s", {user.id}, {str(e)}
        )
        flash(
            "Error during login process. Please try again.",
            FlashAlertTypeEnum.DANGER.value,
        )
        return redirect(url_for("auth.auth"))


@auth_bp.route("/cookies", methods=["GET"])
def get_cookies():
    """Get all cookies."""
    cookies = {}
    for key, value in request.cookies.items():
        cookies[key] = value
    return jsonify(cookies)


@auth_bp.route("/test-jwt", methods=["GET"])
@login_required
def test_jwt():
    """Render the JWT test page."""
    response = make_response(render_template("test_jwt.html"))

    # Ensure CSRF token is set
    if "csrf_token" not in request.cookies:
        csrf = generate_csrf()
        response.set_cookie("csrf_token", csrf)

    return response


@auth_bp.route("/test-auth", methods=["GET"])
@jwt_required()
def test_auth():
    """Test endpoint for JWT authentication."""
    try:
        current_identity = get_jwt_identity()
        user = User.query.get(current_identity)
        if not user:
            return jsonify({"message": "User not found", "status": "error"}), 404

        response = jsonify(
            {
                "message": "Protected endpoint accessed successfully",
                "user_id": current_identity,
                "username": user.username,
                "status": "success",
            }
        )
        return response
    except Exception as e:
        current_app.logger.error(f"Error in test_auth: {str(e)}")
        return (
            jsonify(
                {
                    "message": "Error accessing protected endpoint",
                    "error": str(e),
                    "status": "error",
                }
            ),
            500,
        )


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""

    # Get user identity from refresh token
    user_id = get_jwt_identity()

    # Create new access token
    access_token = create_access_token(identity=user_id)

    # Create response
    response = jsonify({"msg": "Token refreshed successfully"})

    # Set the JWT access cookies in response
    set_access_cookies(response, access_token)

    current_app.logger.info("Access token refreshed for user, id: %s.", {user_id})

    return response


@auth_bp.route("/force-expire", methods=["POST"])
@login_required
def force_expire():
    """Force expire the access token for testing."""
    try:
        # Get current user from Flask-Login session
        if not current_user or not current_user.is_authenticated:
            return (
                jsonify({"message": "User not authenticated", "status": "error"}),
                401,
            )

        # Create an immediately expired token without verifying current token
        expired_token = create_access_token(
            identity=current_user.id,
            expires_delta=timedelta(seconds=-1),  # Set to already expired
        )

        # Create response with expired token info
        response = jsonify(
            {
                "message": "Access token expired",
                "user_id": current_user.id,
                "username": current_user.username,
                "status": "success",
            }
        )

        # Set the expired token in cookies
        set_access_cookies(response, expired_token)

        # Generate new CSRF token
        csrf = generate_csrf()
        response.set_cookie("csrf_token", csrf)

        current_app.logger.info(f"Token expired for user {current_user.id}")
        return response

    except Exception as e:
        current_app.logger.error(f"Error in force_expire: {str(e)}")
        return (
            jsonify(
                {
                    "message": "Failed to expire token",
                    "error": str(e),
                    "status": "error",
                }
            ),
            500,
        )
