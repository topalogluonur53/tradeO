import argparse
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def main():
    parser = argparse.ArgumentParser(description="Create a new user for NEXUS AI TRADER")
    parser.add_argument("username", type=str, help="Username of the new user")
    parser.add_argument("password", type=str, help="Password for the new user")
    parser.add_argument("--admin", action="store_true", help="Create as admin")
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.username == args.username).first()
        if existing_user:
            print(f"Hata: {args.username} kullanici adiyla zaten bir kullanici mevcut.")
            return

        new_user = User(
            username=args.username,
            hashed_password=get_password_hash(args.password),
            is_active=True,
            is_admin=args.admin
        )
        db.add(new_user)
        db.commit()
        print(f"Basarili! Kullanici olusturuldu. (ID: {new_user.id}, Username: {new_user.username})")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
