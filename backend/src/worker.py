import time, json, logging
from pathlib import Path
from sqlalchemy import select, update
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report
from src.services.business import analyze
from src.services.reports import deliver
from src.services.audit import record
logging.basicConfig(level=logging.INFO)
def version_of(dataset):
    return (dataset.current_version or 1) if dataset else None
def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j or j.status!='queued':return
        d=db.get(Dataset,j.dataset_id)
        if j.stale or version_of(d)!=(j.dataset_version or 1):
            # 排队期间样本已更正：不再计算，直接标记被取代
            j.stale=True;j.status='superseded';j.error='样本批次已更正，该任务基于旧版本，被取代';j.finished_at=time.time()
            record(db,'worker','job.superseded',{'id':j.id})
            db.commit();return
        j.status='running'; db.commit()
        try:
            result=analyze(d.records,j.params)
            json.dumps(result,allow_nan=False)
            finalize(db,j,result)
        except Exception as e:
            logging.exception('Analysis failed')
            db.rollback()
            j=db.get(Job,job_id)
            j.status='failed';j.error=str(e)[:990];j.finished_at=time.time()
            record(db,'worker','job.failed',{'id':j.id,'error':j.error})
            db.commit()
def finalize(db,j,result):
    # 纠错与计算同时发生时，用条件更新抢占写入权：
    # 只有仍是 running 且未被标记失效时才落 completed；
    # 否则纠错事务已先提交，晚完成的旧计算只能归档为 superseded，不能覆盖新结果。
    now=time.time()
    won=db.execute(update(Job).where(Job.id==j.id,Job.status=='running',Job.stale==False).values(result=result,status='completed',finished_at=now).execution_options(synchronize_session=False)).rowcount
    if won:
        record(db,'worker','job.completed',{'id':j.id})
        db.commit();return
    db.execute(update(Job).where(Job.id==j.id,Job.status=='running').values(result=result,status='superseded',stale=True,error='计算完成前样本已更正，结果仅存档不采用',finished_at=now).execution_options(synchronize_session=False))
    record(db,'worker','job.superseded',{'id':j.id,'late':True})
    db.commit()
def tick():
    with Session() as db:
        # 兜底：排队中但已失效的任务不再执行（失效传播异常中断时也能收敛）
        for j in db.scalars(select(Job).where(Job.status=='queued',Job.stale==True)):
            j.status='superseded';j.error='样本批次已更正，该任务基于旧版本，被取代';j.finished_at=time.time()
            record(db,'worker','job.superseded',{'id':j.id})
        db.commit()
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued',Job.stale==False).limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.paused==False,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()
def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    # 重启恢复：运行中的任务重新排队；已失效的不再重算，接着完成失效收敛。
    with Session() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')):
            if j.stale:
                j.status='superseded';j.error='样本批次已更正，该任务基于旧版本，被取代';j.finished_at=time.time()
                record(db,'worker','job.superseded',{'id':j.id,'recovered':True})
            else:
                j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
