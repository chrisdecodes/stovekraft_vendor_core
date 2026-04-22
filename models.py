
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()

class Marketplace(Base):
    __tablename__ = "marketplaces"
    
    marketplace_id = Column(String(50), primary_key=True)
    marketplace_name = Column(String(100), nullable=False)
    amazon_marketplace_id = Column(String(50), unique=True, nullable=False)
    region = Column(String(20), nullable=False)  # NA, EU, FE

class Creds(Base):
    __tablename__ = "creds"
    
    cred_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lwa_client_id = Column(Text, nullable=False)      # Encrypted
    lwa_client_secret = Column(Text, nullable=False)  # Encrypted
    refresh_token = Column(Text, nullable=False)      # Encrypted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    stores = relationship("Store", back_populates="creds")

class Store(Base):
    __tablename__ = "stores"
    
    store_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_name = Column(String(100), nullable=False)
    cred_id = Column(String(36), ForeignKey("creds.cred_id"), nullable=False)
    marketplace_id = Column(String(50), ForeignKey("marketplaces.marketplace_id"), nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    
    creds = relationship("Creds", back_populates="stores")
    marketplace = relationship("Marketplace")

class SyncState(Base):
    __tablename__ = "sync_states"
    
    id = Column(Integer, primary_key=True)
    store_id = Column(String(36), ForeignKey("stores.store_id"), nullable=False)
    job_name = Column(String(100), nullable=False)
    last_checkpoint = Column(DateTime, nullable=True)
    last_report_id = Column(String(100), nullable=True)
    status = Column(String(20), default="IDLE") # IDLE, RUNNING, ERROR
    last_error = Column(Text, nullable=True)
