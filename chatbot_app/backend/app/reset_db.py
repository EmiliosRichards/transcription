import asyncio
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app.database import Base, async_engine

async def reset_database():
    print("Resetting database...")
    async with async_engine.begin() as conn:
        print("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Creating all tables...")
        await conn.run_sync(Base.metadata.create_all)
    print("Database has been reset successfully.")

if __name__ == "__main__":
    asyncio.run(reset_database())