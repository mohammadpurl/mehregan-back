from sqlalchemy.orm import Session
from app.models.user import User


def get_user_manager(db: Session, user_id: int):
    user = db.get(User, user_id)

    if not user or not user.manager_id:
        return None

    return db.get(User, user.manager_id)


def get_manager_chain(db: Session, user_id: int, level=3):
    chain = []
    current = db.get(User, user_id)

    while current and current.manager_id and len(chain) < level:
        manager = db.get(User, current.manager_id)
        if not manager:
            break
        chain.append(manager)
        current = manager

    return chain
