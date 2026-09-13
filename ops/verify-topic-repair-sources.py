"""Independent read-only source hashes and current child counts; no answer export."""
import argparse
import asyncio
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from uuid import UUID


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


async def inspect_sources(helper):
    from sqlalchemy import select, text, func
    from app.core.database import AsyncSessionLocal, engine
    from app.models.amway_circle_tracking import (AmwayCircleRun, AmwayCircleAnswer,
        AmwayCircleEvidence, AmwayCircleEntityMention, AmwayCircleNodeSnapshot)
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.models.snapshot import AnalysisSnapshot
    from app.models.task import AnalysisTask
    from app.services.amway_circle_tracking_service import _answer_records
    directory = Path('/srv/ageo-deploy/shared/runtime/topic-repairs/amway-topic-coverage-20260913-v1')
    with gzip.open(directory / 'plan.json.gz', 'rt', encoding='utf-8') as handle:
        plan = json.load(handle)
    expected = '6bcd9f9df876ef2638c7fed93bac7a691e4681200b29028951ccea9784397677'
    if plan['manifest_hash'] != expected or digest({k:v for k,v in plan.items() if k != 'manifest_hash'}) != expected:
        raise ValueError('plan_mismatch')
    result = {'manifest_hash': expected, 'source_hashes': {}, 'answer_bindings': {}, 'target_child_counts': {}}
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            await db.execute(text("SET LOCAL statement_timeout = '45s'"))
            for run_id in sorted(plan['source_answer_hashes']):
                run = await db.get(AmwayCircleRun, UUID(run_id))
                if run is None or run.entity_id != helper.ENTITY_ID:
                    raise ValueError('source_entity_mismatch')
                brand = await db.get(BrandIntelligenceRun, run.brand_intelligence_run_id)
                task = await db.get(AnalysisTask, run.analysis_task_id) if run.analysis_task_id else None
                snapshot_id = (brand.output_refs or {}).get('snapshot_id') if brand else None
                snapshot_id = snapshot_id or (task.snapshot_id if task else None)
                raw = await db.scalar(select(AnalysisSnapshot.raw_data).where(
                    AnalysisSnapshot.id == UUID(str(snapshot_id)), AnalysisSnapshot.entity_id == helper.ENTITY_ID))
                fetch = raw['fetch_results']
                result['source_hashes'][run_id] = digest(fetch)
                records = _answer_records(fetch_results=fetch, source_appendix=[], center_terms=run.center_terms)
                stored = (await db.execute(select(AmwayCircleAnswer.question_id, AmwayCircleAnswer.platform,
                    AmwayCircleAnswer.answer_hash).where(AmwayCircleAnswer.circle_run_id == run.id))).all()
                by_key = {(r.question_id, r.platform): r.answer_hash for r in stored}
                matched = sum(by_key.get((r['question_id'], r['platform'])) == r['answer_hash'] for r in records)
                result['answer_bindings'][run_id] = {'fetch_records': len(records), 'stored_records': len(stored),
                    'matched_records': matched, 'mismatched_records': len(records) - matched}
                del fetch, raw, records, stored, by_key
                db.expunge_all()
            target_ids = [UUID(r) for r in plan['run_ids']]
            for model in (AmwayCircleEvidence, AmwayCircleEntityMention, AmwayCircleNodeSnapshot):
                result['target_child_counts'][model.__tablename__] = await db.scalar(select(func.count()).select_from(model)
                    .where(model.circle_run_id.in_(target_ids)))
            result['database_read_only'] = await db.scalar(text('SHOW transaction_read_only')) == 'on'
            await db.rollback()
        return result
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-release', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('replay_helper', Path(__file__).with_name('replay-topic-nodes.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    try:
        output = helper.configure(args.expected_release, args.output_dir)
        result = asyncio.run(asyncio.wait_for(inspect_sources(helper), timeout=180))
        result['release_sha'] = args.expected_release
        if Path('/srv/ageo-deploy/current/.release-sha').read_text().strip() != args.expected_release:
            raise ValueError('release_changed')
        destination = output / 'sources.json'
        with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
            json.dump(result, handle)
        owner = output.stat()
        os.chown(destination, owner.st_uid, owner.st_gid)
        print(json.dumps(result), flush=True)
    except Exception as exc:
        print(json.dumps({'failed': True, 'failure_type': type(exc).__name__}))
        raise SystemExit(1)
