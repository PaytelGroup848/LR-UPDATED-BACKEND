from backend.extensions import db


def get_db():
    yield db


MongoDatabase = type(db)
