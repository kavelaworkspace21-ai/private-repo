from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.client import Client
from app.models.user import User
from app.auth.dependencies import require_matter_write
from app.services.tenancy import current_tenant_id, get_owned_client, write_audit
from app.schemas.client import ClientCreate, ClientUpdate, ClientOut

router = APIRouter()


@router.get("/", response_model=list[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return (
        db.query(Client)
        .filter(Client.tenant_id == tenant_id)
        .order_by(Client.id)
        .all()
    )


@router.post("/", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    client = Client(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(client)
    db.commit()
    db.refresh(client)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="create_client", entity="Client", entity_id=client.id)
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(current_tenant_id),
):
    return get_owned_client(client_id, tenant_id, db)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    client = get_owned_client(client_id, user.tenant_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="update_client", entity="Client", entity_id=client.id)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_matter_write),
):
    client = get_owned_client(client_id, user.tenant_id, db)
    db.delete(client)
    db.commit()
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="delete_client", entity="Client", entity_id=client_id)
