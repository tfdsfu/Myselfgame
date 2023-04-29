import sqlalchemy
from data.db_session import SqlAlchemyBase
from sqlalchemy_serializer import SerializerMixin


class Categories(SqlAlchemyBase, SerializerMixin):
    __tablename__ = 'categories'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)

    category = sqlalchemy.Column(sqlalchemy.String, nullable=True)

    for i in range(1, 7):
        locals()[f"question{i}"] = sqlalchemy.Column(sqlalchemy.String, nullable=True)

    for i in range(1, 7):
        locals()[f"answer{i}"] = sqlalchemy.Column(sqlalchemy.String, nullable=True)
