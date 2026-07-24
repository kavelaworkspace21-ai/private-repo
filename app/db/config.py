import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./legal_server.db")

if DATABASE_URL.startswith("sqlite"):
    # SQLite (local dev/tests): allow the connection across FastAPI's threads.
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, echo=False,
    )
else:
    # PostgreSQL / Aurora (production on EC2): pool_pre_ping discards stale
    # connections (Aurora closes idle ones and recycles on failover), and
    # pool_recycle keeps the pool fresh behind the cluster endpoint.
    # connect_timeout: fail FAST (5s → clean error) when the cluster is stopped or
    # unreachable, instead of every request hanging on the ~30s driver default
    # (verified during the 2026-06-27 Aurora-stopped incident).
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 5},
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
