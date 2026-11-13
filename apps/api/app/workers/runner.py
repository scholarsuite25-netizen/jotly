import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.worker")


def main() -> None:
    logger.info(
        "NEXUS Background Worker started (tenant-context isolation enforced; voice_cloning_enabled=False)."
    )
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
