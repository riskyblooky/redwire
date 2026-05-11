import asyncio
from database import AsyncSessionLocal
from sqlalchemy import text

async def check():
    tables = ['client_user_access', 'finding_assets', 'infra_item_findings',
              'infra_item_notes', 'infra_item_testcases', 'plugin_settings',
              'plugin_states', 'testcase_assets', 'testcase_tags', 'automation_rules']
    results = []
    async with AsyncSessionLocal() as db:
        for t in tables:
            try:
                r = await db.execute(text(f"SELECT count(*) FROM {t}"))
                c = r.scalar()
                results.append(f"OK    {t} ({c} rows)")
            except Exception as e:
                err = str(e).split('\n')[0][:80]
                results.append(f"MISS  {t} -- {err}")
            finally:
                await db.rollback()
    
    with open('/tmp/table_check.txt', 'w') as f:
        for r in results:
            f.write(r + '\n')

asyncio.run(check())
