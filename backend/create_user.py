import argparse
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def main():
    parser = argparse.ArgumentParser(description="Create a new user for NEXUS AI TRADER")
    parser.add_argument("email", type=str, help="Email address of the new user")
    parser.add_argument("password", type=str, help="Password for the new user")
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.email == args.email).first()
        if existing_user:
            print(f"Hata: {args.email} e-posta adresiyle zaten bir kullanici mevcut.")
            return

        new_user = User(
            email=args.email,
            hashed_password=get_password_hash(args.password),
            is_active=True
        )
        db.add(new_user)
        db.commit()
        print(f"Basarili! Kullanici olusturuldu. (ID: {new_user.id}, Email: {new_user.email})")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
