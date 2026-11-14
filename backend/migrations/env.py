"""Alembic environment: uses the app's settings and model metadata."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db.session import Base
from app.drones import models as drone_models  # noqa: F401  (registers tables on Base.metadata)
from app.events import models as event_models  # noqa: F401  (registers tables)
from app.hubs import models  # noqa: F401  (registers tables on Base.metadata)
from app.missions import models as mission_models  # noqa: F401  (registers tables on Base.metadata)
from app.orders import models as order_models  # noqa: F401  (registers tables on Base.metadata)
from app.simulation import models as simulation_models  # noqa: F401  (registers tables)
from app.weather import models as weather_models  # noqa: F401  (registers tables)

target_metadata = Base.metadata
# A URL set on the Alembic config (e.g. by tests) wins; otherwise use DATABASE_URL from settings.
url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
