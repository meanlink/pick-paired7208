"""样本版本纠错：登记新版本，失效关联分析并自动安排重算。

整个流程在调用方的事务内提交，保证"版本 + 失效 + 重算 + 暂停简报"原子生效，
失败重试或服务重启后不会出现只完成一半的中间态。
"""
import time
from sqlalchemy import select
from src.models import DatasetRevision, Job, Report
from src.utils.serialization import checksum
def apply(db, dataset, action, reason, records, user):
    version = (dataset.current_version or 1) + 1
    revision = DatasetRevision(dataset_id=dataset.id, version=version, action=action, reason=reason, records=records, checksum=checksum(records), created_by=user.id if user else None, created_at=time.time())
    db.add(revision)
    dataset.records = records
    dataset.checksum = revision.checksum
    dataset.current_version = version
    # 排队、运行中、已完成的关联分析全部识别失效
    affected = list(db.scalars(select(Job).where(Job.dataset_id == dataset.id, Job.status.in_(['queued', 'running', 'completed']), Job.stale == False)))
    recalcs = []
    for j in affected:
        j.stale = True
        if j.status == 'queued':
            # 排队任务不再执行，直接标记被取代；运行中的由 worker 完成时识别
            j.status = 'superseded'
            j.error = f'样本已更正为 v{version}，该排队任务基于旧版本，被取代'
            j.finished_at = time.time()
        recalc = Job(name=f'{j.name} · 重算v{version}', dataset_id=dataset.id, dataset_version=version, params=dict(j.params or {}), status='queued', created_by=user.id if user else j.created_by, created_at=time.time(), recalc_of=j.id)
        db.add(recalc)
        recalcs.append(recalc)
    # 已批准简报暂停采用旧结论，等待重算复核后恢复
    paused = []
    approved_ids = [j.id for j in affected if j.approved]
    if approved_ids:
        for r in db.scalars(select(Report).where(Report.job_id.in_(approved_ids), Report.paused == False)):
            r.paused = True
            paused.append(r)
    db.flush()
    return revision, affected, recalcs, paused
