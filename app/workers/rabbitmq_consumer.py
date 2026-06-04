import asyncio
from app.infrastructure.messaging.consumer import start_consumer


async def main():
    await start_consumer()


if __name__ == "__main__":
    asyncio.run(main())
