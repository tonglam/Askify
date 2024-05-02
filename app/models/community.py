"""Community model."""

import datetime

from app.extensions import db
from app.utils import generate_time


class Community(db.Model):
    """Community model."""

    id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name: str = db.Column(db.String(20), unique=True, nullable=False)
    category_id: int = db.Column(db.Integer, db.ForeignKey("category.id"))
    description: str = db.Column(db.String(500))
    avatar_url: str = db.Column(db.String(300))
    create_at: datetime = db.Column(db.DateTime, default=generate_time())
    update_at: datetime = db.Column(
        db.DateTime, default=generate_time(), onupdate=generate_time()
    )

    category = db.relationship("Category", backref=db.backref("communities", lazy=True))

    __searchable__ = ["name", "description"]

    def __init__(
        self, name: str, category_id: int, description: str = "", avatar_url: str = ""
    ) -> None:
        self.name = name
        self.category_id = category_id
        self.description = description
        self.avatar_url = avatar_url

    def __repr__(self) -> str:
        """Return a string representation of the community."""

        return f"<Community {self.name}>"

    # genrated by copilot
    def to_dict(self) -> dict:
        """Return a JSON format of the community."""

        return {
            "id": self.id,
            "name": self.name,
            "category_id": self.category_id,
            "description": self.description,
            "avatar_url": self.avatar_url,
            "create_at": self.create_at,
            "update_at": self.update_at,
        }
