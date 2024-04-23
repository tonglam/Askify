"""Request model."""

from app.extensions import db
from app.utils import generate_time


# pylint: disable=too-many-instance-attributes
class Request(db.Model):
    """Request model."""

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    community = db.Column(db.Integer, db.ForeignKey("community.id"), nullable=False)
    author = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(40), nullable=False)
    content = db.Column(db.String(1000), default="")
    category = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    view_num = db.Column(db.Integer)
    like_num = db.Column(db.Integer)
    reply_num = db.Column(db.Integer)
    save_num = db.Column(db.Integer)
    create_at = db.Column(db.DateTime, default=generate_time())
    update_at = db.Column(
        db.DateTime, default=generate_time(), onupdate=generate_time()
    )

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        community: int,
        author: str,
        title: str,
        content: str,
        category: int,
        view_num: int,
        like_num: int,
        reply_num: int,
        save_num: int,
    ) -> None:
        self.community = community
        self.author = author
        self.title = title
        self.content = content
        self.category = category
        self.view_num = view_num
        self.like_num = like_num
        self.reply_num = reply_num
        self.save_num = save_num

    def __repr__(self) -> str:
        """Return a string representation of the request."""

        return f"<Request {self.id}>"

    # genrated by copilot
    def to_dict(self):
        """Return a JSON format of the request."""

        return {
            "id": self.id,
            "community": self.community,
            "author": self.author,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "view_num": self.view_num,
            "like_num": self.like_num,
            "reply_num": self.reply_num,
            "save_num": self.save_num,
            "create_at": self.create_at,
            "update_at": self.update_at,
        }
