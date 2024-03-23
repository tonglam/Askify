# pylint: skip-file

from flask import Blueprint

community_bp = Blueprint(
    "community",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/community/static",
)

from . import routes
