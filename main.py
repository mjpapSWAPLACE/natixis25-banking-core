from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from database import get_db, init_db, User, Account, Transfer
from schemas import (
    UserCreate, UserResponse,
    AccountCreate, AccountResponse,
    TransferCreate, TransferResponse
)

async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Core Banking API", version="1.0.0", lifespan=lifespan)


def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> User:
    try:
        user_id = int(authorization)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    user = User(name=user_data.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information"""
    return current_user


@app.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(
    account_data: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new account for the authenticated user"""
    account = Account(
        user_id=current_user.id,
        account_type=account_data.account_type,
        currency=account_data.currency.upper(),
        balance=account_data.balance
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@app.get("/accounts", response_model=List[AccountResponse])
def list_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all accounts for the authenticated user"""
    accounts = db.query(Account).filter(Account.user_id == current_user.id).all()
    return accounts


@app.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific account"""
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return account

@app.post("/transfers", response_model=TransferResponse, status_code=201)
def create_transfer(
    transfer_data: TransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Transfer money between accounts"""
    from_account = db.query(Account).filter(
        Account.id == transfer_data.from_account_id
    ).first()

    if not from_account:
        raise HTTPException(status_code=404, detail="Source account not found")


    if from_account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don't own the source account")


    to_account = db.query(Account).filter(
        Account.id == transfer_data.to_account_id
    ).first()

    if not to_account:
        raise HTTPException(status_code=404, detail="Destination account not found")


    if from_account.currency != to_account.currency:
        raise HTTPException(
            status_code=400,
            detail=f"Currency mismatch: {from_account.currency} != {to_account.currency}"
        )


    if from_account.balance < transfer_data.amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: {from_account.balance}"
        )

    if transfer_data.from_account_id == transfer_data.to_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")


    from_account.balance -= transfer_data.amount
    to_account.balance += transfer_data.amount


    transfer = Transfer(
        from_account_id=transfer_data.from_account_id,
        to_account_id=transfer_data.to_account_id,
        amount=transfer_data.amount
    )

    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    return transfer


@app.get("/transfers", response_model=List[TransferResponse])
def list_transfers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all transfers for the authenticated user's accounts"""
    account_ids = [acc.id for acc in current_user.accounts]

    transfers = db.query(Transfer).filter(
        (Transfer.from_account_id.in_(account_ids)) |
        (Transfer.to_account_id.in_(account_ids))
    ).all()

    return transfers


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
