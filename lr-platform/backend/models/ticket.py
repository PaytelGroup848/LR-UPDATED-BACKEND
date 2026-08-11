from datetime import datetime
from backend.extensions import db


class Ticket:

    collection = db["tickets"]

    @staticmethod
    def create(data):

        ticket = {
            "title": data.get("title"),
            "description": data.get("description", ""),
            "status": data.get("status", "open"),
            "priority": data.get("priority", "normal"),
            "created_by": data.get("created_by"),
            "assigned_to": data.get("assigned_to"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "closed_at": None
        }

        result = Ticket.collection.insert_one(ticket)
        ticket["_id"] = result.inserted_id
        return ticket

    @staticmethod
    def update(ticket_id, data):
        from bson import ObjectId

        data["updated_at"] = datetime.utcnow()

        # agar status closed ho gaya to closed_at set karo
        if data.get("status") == "closed":
            data["closed_at"] = datetime.utcnow()

        return Ticket.collection.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": data}
        )

    @staticmethod
    def get_all():
        return list(Ticket.collection.find().sort("created_at", -1))

    @staticmethod
    def get_by_id(ticket_id):
        from bson import ObjectId
        try:
            return Ticket.collection.find_one({"_id": ObjectId(ticket_id)})
        except:
            return None

    @staticmethod
    def to_dict(ticket):
        return {
            "id": str(ticket.get("_id")),
            "title": ticket.get("title"),
            "description": ticket.get("description", ""),
            "status": ticket.get("status"),
            "priority": ticket.get("priority"),
            "created_by": ticket.get("created_by"),
            "assigned_to": ticket.get("assigned_to"),
            "created_at": ticket.get("created_at").isoformat() if ticket.get("created_at") else None,
            "updated_at": ticket.get("updated_at").isoformat() if ticket.get("updated_at") else None,
            "closed_at": ticket.get("closed_at").isoformat() if ticket.get("closed_at") else None,
        }
class ClipboardItem:

    collection = db["clipboard_items"]

    @staticmethod
    def create(user_id, content, session_id=None, direction="web_to_remote"):

        item = {
            "user_id": user_id,
            "session_id": session_id,
            "direction": direction,
            "content": content,
            "created_at": datetime.utcnow()
        }

        result = ClipboardItem.collection.insert_one(item)
        item["_id"] = result.inserted_id
        return item

    @staticmethod
    def get_by_user(user_id):
        return list(
            ClipboardItem.collection.find({"user_id": user_id})
            .sort("created_at", -1)
        )

    @staticmethod
    def get_by_session(session_id):
        return list(
            ClipboardItem.collection.find({"session_id": session_id})
            .sort("created_at", -1)
        )

    @staticmethod
    def delete(item_id):
        from bson import ObjectId
        return ClipboardItem.collection.delete_one({"_id": ObjectId(item_id)})

    @staticmethod
    def to_dict(item):
        return {
            "id": str(item.get("_id")),
            "user_id": item.get("user_id"),
            "session_id": item.get("session_id"),
            "direction": item.get("direction"),
            "content": item.get("content"),
            "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
        }   