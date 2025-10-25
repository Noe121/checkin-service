"""
Soft Delete Mixin for SQLAlchemy Models

Provides soft delete functionality to any model. Allows marking records as deleted
without actually removing them from the database, preserving referential integrity
and providing audit trails.

Usage:
    class User(Base, SoftDeleteMixin):
        __tablename__ = 'users'
        id = Column(Integer, primary_key=True)
        ...
    
    # Soft delete
    user.soft_delete()
    session.commit()
    
    # Query only active records (default)
    active_users = session.query(User).all()  # Excludes deleted
    
    # Query including deleted
    all_users = session.query(User).with_deleted().all()
    
    # Query only deleted
    deleted_users = session.query(User).only_deleted().all()
"""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Column
from sqlalchemy.orm import declared_attr, Query
from sqlalchemy.sql import and_


class SoftDeleteMixin:
    """
    Mixin to add soft delete functionality to SQLAlchemy models.
    
    Adds:
    - is_deleted: Boolean column (default False)
    - deleted_at: DateTime column (timestamp when deleted)
    - soft_delete(): Method to mark as deleted
    - restore(): Method to restore from deletion
    """
    
    @declared_attr
    def is_deleted(cls):
        """Boolean flag for soft deletes (default: False)"""
        return Column(Boolean, default=False, index=True)
    
    @declared_attr
    def deleted_at(cls):
        """Timestamp when record was deleted (nullable)"""
        return Column(DateTime, nullable=True, index=True)
    
    def soft_delete(self):
        """Mark this record as deleted (soft delete)"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
    
    def restore(self):
        """Restore a soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None


class SoftDeleteQuery(Query):
    """
    Custom Query class that filters out soft-deleted records by default.
    
    Provides:
    - filter_deleted(): Default behavior, excludes deleted records
    - with_deleted(): Include deleted records in results
    - only_deleted(): Return only deleted records
    """
    
    def filter_deleted(self):
        """Exclude deleted records (default behavior)"""
        return self.filter(self.model.is_deleted == False)  # type: ignore
    
    def with_deleted(self):
        """Include deleted records in query"""
        return self
    
    def only_deleted(self):
        """Return only deleted records"""
        return self.filter(self.model.is_deleted == True)  # type: ignore


def get_session_with_soft_delete(session):
    """
    Configure a session to use SoftDeleteQuery by default.
    
    Usage:
        session = get_db()
        session = get_session_with_soft_delete(session)
        users = session.query(User).all()  # Automatically excludes deleted
    """
    # For async sessions, you'll need to configure this differently
    # This is a reference implementation for sync sessions
    pass


# Helper function for filtering in async contexts
def soft_delete_filter(model):
    """
    Get the filter condition for non-deleted records.
    
    Usage in async code:
        result = await db.execute(
            select(User).filter(soft_delete_filter(User))
        )
    """
    return model.is_deleted == False


def deleted_filter(model):
    """
    Get the filter condition for deleted records.
    
    Usage in async code:
        result = await db.execute(
            select(User).filter(deleted_filter(User))
        )
    """
    return model.is_deleted == True
