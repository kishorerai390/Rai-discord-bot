import sys, os
sys.path.insert(0, os.path.abspath("."))

import asyncio
import datetime
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import discord
from config.permissions import PermissionLevel
from core.workflow import WorkflowEngine, WorkflowStatus, ActionRiskLevel
from database.database import Database
from database.models import Workflow, WorkflowStep

logging.basicConfig(level=logging.INFO)

async def main():
    guild_id = 1457382179981099090
    owner_id = 999888777

    # Initialize live Database with real data/bot.db
    db = Database(db_path="data/bot.db")
    await db.connect()

    # Mock Discord objects for live engine invocation
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.name = "RAI Production Discord"
    guild.owner_id = owner_id

    owner = MagicMock(spec=discord.Member)
    owner.id = owner_id
    owner.guild_permissions = MagicMock()
    owner.guild_permissions.administrator = True
    guild.get_member = MagicMock(return_value=owner)

    bot = MagicMock()
    bot.db = db
    bot.get_guild = MagicMock(return_value=guild)

    wf_id = "wf_rai_system_test"

    # Clean existing if needed
    existing = await db.get_workflow(wf_id)
    if existing:
        await db.delete_workflow(wf_id)
        await db.delete_workflow_steps(wf_id)

    # 1. Create Workflow Record
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    wf = Workflow(
        id=wf_id,
        guild_id=guild_id,
        creator_id=owner_id,
        name="Rai System Test",
        description="Core system verification workflow executing health check and report generation",
        status=WorkflowStatus.ACTIVE.value,
        trigger_type="manual",
        trigger_config={},
        created_at=now,
        updated_at=now,
    )
    await db.create_workflow(wf)
    print(f"Created workflow: {wf.name} ({wf.id})")

    # 2. Add Step 1: Health Check
    step1 = WorkflowStep(
        id=f"step_{wf_id}_1",
        workflow_id=wf_id,
        step_order=1,
        action_type="health.check",
        action_config={},
        risk_level="LOW",
        failure_policy="STOP",
        timeout_seconds=30,
    )
    await db.add_workflow_step(step1)
    print("Added Step 1: health.check")

    # 3. Add Step 2: Report Generation / Send
    step2 = WorkflowStep(
        id=f"step_{wf_id}_2",
        workflow_id=wf_id,
        step_order=2,
        action_type="report.send",
        action_config={"summary": "Rai System Test verified all internal subsystems are operational."},
        risk_level="LOW",
        failure_policy="STOP",
        timeout_seconds=30,
    )
    await db.add_workflow_step(step2)
    print("Added Step 2: report.send")

    # 4. Execute Workflow
    print("\n--- Executing Workflow Engine ---")
    res = await WorkflowEngine.execute_workflow(
        bot,
        guild,
        wf_id,
        trigger_event="system_test_execution",
        actor=owner,
        is_simulation=False,
    )
    print("Execution Result:", json.dumps(res, indent=2))

    exec_id = res.get("execution_id")
    status = res.get("status")

    # 5. Verify Database Records
    print("\n--- Verifying SQLite Persistence in data/bot.db ---")
    exec_rec = await db.get_workflow_execution(exec_id)
    step_execs = await db.list_step_executions(exec_id)

    print(f"Execution ID in DB: {exec_rec.id if exec_rec else 'None'}")
    print(f"Execution Status in DB: {exec_rec.status if exec_rec else 'None'}")
    print(f"Step Executions Count in DB: {len(step_execs)}")
    for sx in step_execs:
        print(f"  Step ID: {sx.step_id} | Status: {sx.status} | Attempt: {sx.attempt} | Result: {sx.result_json}")

    await db.close()

    assert status == "SUCCESS", f"Expected SUCCESS, got {status}"
    assert exec_rec is not None, "Execution record not found in database!"
    assert exec_rec.status == "COMPLETED", f"Expected COMPLETED, got {exec_rec.status}"
    assert len(step_execs) == 2, f"Expected 2 step executions, got {len(step_execs)}"

    print("\n[SUCCESS] ALL VERIFICATIONS PASSED!")

if __name__ == "__main__":
    asyncio.run(main())
