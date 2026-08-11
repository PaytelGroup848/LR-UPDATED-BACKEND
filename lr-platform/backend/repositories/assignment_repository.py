from backend.models.assignment import ApplicationAssignment


class AssignmentRepository:
    def __init__(self, db=None):
        self.collection = (
            ApplicationAssignment.collection
            if db is None
            else db["application_assignments"]
        )

    def get_all(self):
        return list(self.collection.find().sort("assigned_at", -1))

    def assign(self, user_id, app_id):
        return ApplicationAssignment.assign(user_id, app_id)

    def find(self, user_id, app_id):
        return ApplicationAssignment.find(user_id, app_id)

    def delete(self, assignment_id):
        from bson import ObjectId

        return self.collection.delete_one({"_id": ObjectId(str(assignment_id))})
