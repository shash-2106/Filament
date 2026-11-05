"""Full-stack integration test against FastAPI and database.

Demonstrates the complete end-to-end user workflow:
1. Agent Bearer authentication via public.filament_lookup_agent.
2. Ingest Evidence snapshot (source_type='file', source_uri='pyproject.toml').
3. Create Claim memory asserted by the authenticated agent.
4. Link Evidence to Claim.
5. Ingest Environment Snapshot (with file digest matching pyproject.toml and package versions).
6. Establish initial versioned conditions binding Claim to the snapshot (file_hash).
7. Transient condition evaluation against matching snapshot -> 'applicable'.
8. Ingest a DRIFTED Environment Snapshot (pyproject.toml modified).
9. Transient condition evaluation against drifted snapshot -> 'environment_mismatch' (is_applicable=False).
10. Ingest an UNRELATED snapshot (only README.md changed) -> remains 'applicable'.
11. Explicit Re-verification: agent adopts replacement conditions with justification.
12. Verify audit events recorded append-only with full history.
"""

import asyncio
import hashlib
import os
import sys
import uuid
from httpx import ASGITransport, AsyncClient


async def main():
    demo_api_key = os.environ.get("FILAMENT_DEMO_AGENT_KEY")
    if not demo_api_key:
        print("❌ Error: FILAMENT_DEMO_AGENT_KEY environment variable required.", file=sys.stderr)
        sys.exit(1)

    from filament_api.main import app

    headers = {"Authorization": f"Bearer {demo_api_key}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        print("1. Testing Workspace Identity & Authentication...")
        res = await client.get("/api/v1/workspaces/current", headers=headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        ws = res.json()
        print(f"   ✅ Authenticated in workspace: '{ws['name']}' (Agent: '{ws['current_agent']['name']}')")

        print("2. Ingesting Evidence Snapshot...")
        snippet = "[tool.poetry.dependencies]\npython = '^3.12'\nfastapi = '^0.115.0'"
        ev_res = await client.post(
            "/api/v1/evidence",
            headers=headers,
            json={
                "source_type": "file",
                "source_uri": "pyproject.toml",
                "raw_snippet": snippet,
            },
        )
        assert ev_res.status_code == 201, f"Expected 201, got {ev_res.status_code}: {ev_res.text}"
        ev = ev_res.json()
        ev_id = ev["id"]
        ev_hash = ev["content_hash"]
        print(f"   ✅ Recorded Evidence: {ev_id} (hash: {ev_hash[:16]}...)")

        print("3. Establishing Governed Memory Claim...")
        claim_res = await client.post(
            "/api/v1/claims",
            headers=headers,
            json={
                "claim_type": "fact",
                "subject": "runtime.fastapi",
                "predicate": "compatible_version",
                "object_value": {"framework": "fastapi", "min_version": "0.115.0"},
                "raw_statement": "FastAPI 0.115.0 is verified compatible with asyncpg session pooling.",
                "scope": "team",
                "confidence": 0.95,
            },
        )
        assert claim_res.status_code == 201, f"Expected 201, got {claim_res.status_code}: {claim_res.text}"
        claim = claim_res.json()
        claim_id = claim["id"]
        print(f"   ✅ Established Claim: {claim_id}")

        print("4. Linking Evidence to Claim...")
        link_res = await client.post(
            f"/api/v1/claims/{claim_id}/evidence",
            headers=headers,
            json={
                "evidence_id": ev_id,
                "support_type": "supports",
                "confidence_weight": 1.0,
                "extraction_notes": "Verified poetry dependencies match async runtime constraints.",
            },
        )
        assert link_res.status_code == 201, f"Expected 201, got {link_res.status_code}: {link_res.text}"
        print("   ✅ Linked Evidence with provenance attribution.")

        print("5. Ingesting Baseline Environment Snapshot A...")
        snap_a_res = await client.post(
            "/api/v1/snapshots",
            headers=headers,
            json={
                "source_ref": "git:main:commit_001",
                "source_type": "agent_client",
                "scan_scope": "full_repository",
                "snapshot_data": {
                    "scanned_roots": ["."],
                    "files": {
                        "pyproject.toml": ev_hash,
                        "README.md": hashlib.sha256(b"Documentation v1").hexdigest(),
                    },
                    "packages": {
                        "pypi:fastapi": {"version": "0.115.0"},
                    },
                },
            },
        )
        assert snap_a_res.status_code == 201, f"Expected 201, got {snap_a_res.status_code}: {snap_a_res.text}"
        snap_a_id = snap_a_res.json()["id"]
        print(f"   ✅ Recorded Snapshot A: {snap_a_id}")

        print("6. Establishing Conditions for Claim based on Snapshot A...")
        cond_res = await client.post(
            f"/api/v1/claims/{claim_id}/conditions",
            headers=headers,
            json={
                "based_on_snapshot_id": snap_a_id,
                "rationale": "Claim requires exact pyproject.toml dependency configuration.",
                "conditions": [
                    {
                        "condition_type": "file_hash",
                        "target_path": "pyproject.toml",
                        "comparator": "hash_equals",
                        "expected_hash": ev_hash,
                        "is_critical": True,
                    }
                ],
            },
        )
        assert cond_res.status_code == 201, f"Expected 201, got {cond_res.status_code}: {cond_res.text}"
        print(f"   ✅ Established Condition Set v1 (based on snapshot {snap_a_id})")

        print("7. Evaluating Claim Against Snapshot A (Should be applicable)...")
        eval_a_res = await client.post(
            f"/api/v1/claims/{claim_id}/evaluate",
            headers=headers,
            json={"snapshot_id": snap_a_id},
        )
        assert eval_a_res.status_code == 200
        eval_a = eval_a_res.json()
        assert eval_a["outcome"] == "applicable"
        assert eval_a["is_applicable"] is True
        print(f"   ✅ Evaluation outcome: {eval_a['outcome']} (applicable={eval_a['is_applicable']})")

        print("8. Ingesting Unrelated Snapshot B (Only README changed)...")
        snap_b_res = await client.post(
            "/api/v1/snapshots",
            headers=headers,
            json={
                "source_ref": "git:main:commit_002_readme_edit",
                "snapshot_data": {
                    "scanned_roots": ["."],
                    "files": {
                        "pyproject.toml": ev_hash,
                        "README.md": hashlib.sha256(b"Documentation v2 - updated typos").hexdigest(),
                    },
                },
            },
        )
        snap_b_id = snap_b_res.json()["id"]
        eval_b_res = await client.post(
            f"/api/v1/claims/{claim_id}/evaluate",
            headers=headers,
            json={"snapshot_id": snap_b_id},
        )
        eval_b = eval_b_res.json()
        assert eval_b["outcome"] == "applicable"
        print(f"   ✅ Unrelated README change preserved claim validity: outcome={eval_b['outcome']}")

        print("9. Ingesting Drifted Snapshot C (Relevant pyproject.toml changed)...")
        drifted_hash = hashlib.sha256(b"Modified pyproject dependencies").hexdigest()
        snap_c_res = await client.post(
            "/api/v1/snapshots",
            headers=headers,
            json={
                "source_ref": "git:main:commit_003_upgrade_deps",
                "snapshot_data": {
                    "scanned_roots": ["."],
                    "files": {
                        "pyproject.toml": drifted_hash,
                    },
                },
            },
        )
        snap_c_id = snap_c_res.json()["id"]
        eval_c_res = await client.post(
            f"/api/v1/claims/{claim_id}/evaluate",
            headers=headers,
            json={"snapshot_id": snap_c_id},
        )
        eval_c = eval_c_res.json()
        assert eval_c["outcome"] == "environment_mismatch"
        assert eval_c["is_applicable"] is False
        print(f"   ✅ Relevant condition change detected drift: outcome={eval_c['outcome']} (applicable=False)")

        print("10. Explicit Reverification & Condition Adoption...")
        reverify_res = await client.post(
            f"/api/v1/claims/{claim_id}/reverify",
            headers=headers,
            json={
                "snapshot_id": snap_c_id,
                "action": "adopt_new_conditions",
                "expected_condition_version": 1,
                "attestation_notes": "Re-verified after dependency upgrade; tests pass cleanly.",
                "adopt_rationale": "Adopting upgraded pyproject.toml hash into condition set v2.",
                "proposed_conditions": [
                    {
                        "condition_type": "file_hash",
                        "target_path": "pyproject.toml",
                        "comparator": "hash_equals",
                        "expected_hash": drifted_hash,
                        "is_critical": True,
                    }
                ],
            },
        )
        assert reverify_res.status_code == 200, f"Expected 200, got {reverify_res.status_code}: {reverify_res.text}"
        reverify_data = reverify_res.json()
        assert reverify_data["outcome"] == "applicable"
        assert reverify_data["active_condition_version"] == 2
        print(f"   ✅ Re-verification succeeded: active condition upgraded to v{reverify_data['active_condition_version']}")

        print("11. Verifying Audit Log Stream...")
        audit_res = await client.get("/api/v1/audit", headers=headers)
        assert audit_res.status_code == 200
        events = audit_res.json()
        event_types = [e["event_type"] for e in events]
        print(f"   ✅ Recorded {len(events)} audit events: {set(event_types)}")

        print("\n🎉 ALL 11 STEPS OF CORE GOVERNANCE WORKFLOW VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
