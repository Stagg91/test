from src.database import SessionLocal, Notification
import time

class NotificationManager:
    @staticmethod
    def send(title, message):
        """
        Logs a notification to the DB.
        In a real PWA with Push, this would also trigger Web Push.
        """
        print(f"[NOTIFICATION] {title}: {message}")
        db = SessionLocal()
        try:
            notif = Notification(
                title=title,
                message=message,
                timestamp=time.time(),
                read=False
            )
            db.add(notif)
            db.commit()
        except Exception as e:
            print(f"Error saving notification: {e}")
        finally:
            db.close()

    @staticmethod
    def get_unread(limit=10):
        db = SessionLocal()
        try:
            notifs = db.query(Notification).filter(Notification.read == False).order_by(Notification.timestamp.desc()).limit(limit).all()
            return notifs
        finally:
            db.close()
