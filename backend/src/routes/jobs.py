from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Job, Report
from src.schemas.job import JobInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import jobs
from src.services.audit import record
from src.utils.serialization import job_dict
router=APIRouter(prefix='/jobs')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [job_dict(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(100))]
@router.post('',status_code=201)
def create(data:JobInput,db=Depends(get_db),u=Depends(can_write)):
    j=jobs.create(db,data,u); record(db,u.email,'job.create',{'id':j.id,'params':j.params})
    db.commit(); jobs.enqueue(j.id); return job_dict(j)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    return job_dict(j)
@router.post('/{id}/approve')
def approve(id:int,db=Depends(get_db),u=Depends(admin_only)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    if j.status!='completed':raise HTTPException(409,'仅已完成结果可以批准')
    if j.stale:raise HTTPException(409,'该结果基于已更正的旧样本，不能批准，请等待重算复核')
    j.approved=True; record(db,u.email,'job.approve',{'id':id})
    # 复核通过：恢复同批次因样本更正而暂停的分发计划，改用新结论
    resumed=[]
    for r in db.scalars(select(Report).join(Job,Report.job_id==Job.id).where(Job.dataset_id==j.dataset_id,Report.paused==True)):
        r.job_id=j.id; r.paused=False; resumed.append(r.id)
        record(db,u.email,'report.resumed',{'id':r.id,'job_id':j.id})
    db.commit()
    return {**job_dict(j),'resumed_reports':resumed}
@router.post('/{id}/retry')
def retry(id:int,db=Depends(get_db),u=Depends(can_write)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    jobs.retry(db,j); record(db,u.email,'job.retry',{'id':id,'dataset_version':j.dataset_version})
    db.commit(); jobs.enqueue(j.id)
    return job_dict(j)
