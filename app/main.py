"""robyn-ml-api - ML API Template powered by Robyn."""

from robyn import Robyn

from app.api.health import router as health_router
from app.core.lifespan import create_lifespan
from app.core.logger import logger
from app.core.settings import settings as st

app = Robyn(__file__)

lifespan = create_lifespan(app)
# Register your events here:
# lifespan.register(ProcessPoolEvent)

app.startup_handler(lifespan.startup)
app.shutdown_handler(lifespan.shutdown)
app.include_router(health_router)


def main() -> None:
    logger.info("🚀 STARTING %s | HOST=%s | PORT=%s", st.API_NAME, st.API_HOST, st.API_PORT)
    app.start(host=st.API_HOST, port=st.API_PORT)


if __name__ == "__main__":
    main()
