"""Seed a persistent demo workspace and registered agent in Supabase or local DB."""

import asyncio
import hashlib
import os
import sys
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Read API key from environment, or generate a cryptographically random one if omitted
DEMO_API_KEY = os.environ.get("FILAMENT_DEMO_AGENT_KEY") or f"fil_live_demo_{uuid.uuid4().hex}"
DEMO_KEY_HASH = hashlib.sha256(DEMO_API_KEY.encode()).hexdigest()

WS_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AGENT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def seed(database_url: str):
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # 1. Upsert Workspace
        await conn.execute(
            text(
                """
                INSERT INTO public.workspaces (id, name, slug)
                VALUES (:id, 'Filament Core Workspace', 'filament-core')
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, slug = EXCLUDED.slug;
                """
            ),
            {"id": WS_ID},
        )

        # 2. Upsert Agent
        await conn.execute(
            text(
                """
                INSERT INTO public.agents (id, workspace_id, name, default_scope, api_key_hash, is_active)
                VALUES (:id, :ws_id, 'Primary Research Agent', 'team', :hash, true)
                ON CONFLICT (id) DO UPDATE SET api_key_hash = EXCLUDED.api_key_hash, is_active = true;
                """
            ),
            {"id": AGENT_ID, "ws_id": WS_ID, "hash": DEMO_KEY_HASH},
        )
    await engine.dispose()
    print("✅ Seeded Workspace 'Filament Core Workspace' and Agent 'Primary Research Agent'")
    print(f"DEMO_AGENT_KEY={DEMO_API_KEY}")


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL required", file=sys.stderr)
        sys.exit(1)
    asyncio.run(seed(url))
