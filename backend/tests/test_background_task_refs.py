"""Fire-and-forget tasks in utils.collaboration are kept referenced until
they finish (the loop holds tasks weakly)."""

from __future__ import annotations

import asyncio


async def test_spawn_holds_task_until_done():
    from utils import collaboration
    gate = asyncio.Event()
    done = []

    async def work():
        await gate.wait()
        done.append(1)

    collaboration._spawn(asyncio.get_running_loop(), work())
    assert len(collaboration._background_tasks) >= 1
    gate.set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert done == [1] and not collaboration._background_tasks
