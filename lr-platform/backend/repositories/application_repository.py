from backend.models.application import PublishedApp


class ApplicationRepository:
    def __init__(self, db=None):
        self.collection = PublishedApp.collection if db is None else db["published_apps"]

    def get_all(self):
        return list(self.collection.find().sort("name", 1))

    def get_by_id(self, app_id):
        return PublishedApp.get_by_id(app_id)

    def create(self, data):
        return PublishedApp.create(data)

    def update(self, app_id, data):
        PublishedApp.update(app_id, data)
        return PublishedApp.get_by_id(app_id)

    def delete(self, app_id):
        return PublishedApp.delete(app_id)
