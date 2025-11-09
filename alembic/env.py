from logging.config import fileConfig
import logging

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import types as sqltypes
from sqlalchemy.dialects.postgresql import JSONB

from alembic import context

# Set up logger for autogenerate tracking
logger = logging.getLogger(__name__)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.database import Base
from app.models import *  # Import all models

target_metadata = Base.metadata

# Indexes that exist in the database but are managed manually (not in models)
# These are performance indexes created in migrations, not defined in SQLAlchemy models
MANAGED_INDEXES = {
    'idx_properties_features_gin',
    'idx_property_bathrooms',
    'idx_property_bedrooms',
    'idx_property_city_state',
    'idx_property_city_state_zip',
    'idx_property_created_at',
    'idx_property_is_featured',
    'idx_property_price',
    'idx_property_square_feet',
    'idx_property_status',
    'idx_property_type',
    'idx_property_year_built',
}


def include_name(name, type_, parent_names):
    """
    Filter function to exclude manually-managed indexes from autogenerate.
    These indexes exist in the database but are not defined in SQLAlchemy models
    because they were created in migrations for performance optimization.
    
    Logs excluded indexes for tracking purposes.
    """
    if type_ == "index" and name in MANAGED_INDEXES:
        # Get table name for logging context
        table_name = parent_names.get("table_name", "unknown")
        schema_name = parent_names.get("schema_name")
        if schema_name:
            full_table = f"{schema_name}.{table_name}"
        else:
            full_table = table_name
        
        logger.info(f"Skipping manually managed index: {name} (table: {full_table})")
        print(f"Skipping manually managed index: {name} (table: {full_table})")
        return False  # Exclude this index from autogenerate
    return True  # Include everything else


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """
    Custom type comparison function that treats JSON and JSONB as equivalent.
    This prevents Alembic from trying to "fix" JSONB columns back to JSON,
    which would remove performance benefits (indexes, faster queries).
    
    Returns True if there ARE differences, False if types are equivalent,
    or None to use the default comparison.
    """
    # Check if both are JSON-related types
    is_inspected_json = isinstance(inspected_type, (sqltypes.JSON, JSONB)) or (
        hasattr(inspected_type, '_type_affinity') and 
        inspected_type._type_affinity == sqltypes.JSON
    )
    is_metadata_json = isinstance(metadata_type, (sqltypes.JSON, JSONB)) or (
        hasattr(metadata_type, '_type_affinity') and 
        metadata_type._type_affinity == sqltypes.JSON
    )
    
    # If both are JSON types, treat them as equivalent (no difference)
    if is_inspected_json and is_metadata_json:
        return False
    
    # For all other types, use the default comparison (return None)
    return None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=compare_type,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
