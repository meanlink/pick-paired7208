from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset, DatasetRevision
from src.schemas.dataset import DatasetInput, CorrectInput, WithdrawInput
from src.middlewares.auth import current_user, can_write
from src.services import datasets, jobs
from src.services.audit import record
from src.utils.serialization import dataset_dict, revision_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
@router.post('',status_code=201)
def create(data:DatasetInput,db=Depends(get_db),u=Depends(can_write)):
    d=datasets.create(db,data,u); record(db,u.email,'dataset.create',{'id':d.id,'rows':len(d.records)})
    db.commit(); return dataset_dict(d)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return {**dataset_dict(d),'records':d.records}
@router.get('/{id}/revisions')
def revisions(id:int,db=Depends(get_db),u=Depends(current_user)):
    if not db.get(Dataset,id):raise HTTPException(404,'数据批次不存在')
    return [revision_dict(r) for r in db.scalars(select(DatasetRevision).where(DatasetRevision.dataset_id==id).order_by(DatasetRevision.version.desc()))]
@router.post('/{id}/correct',status_code=201)
def correct(id:int,data:CorrectInput,db=Depends(get_db),u=Depends(can_write)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    revision,affected,recalcs,paused=datasets.correct(db,d,data,u)
    record(db,u.email,'dataset.correct',{'id':d.id,'version':revision.version,'invalidated':[j.id for j in affected],'recalcs':[j.id for j in recalcs],'paused_reports':[r.id for r in paused]})
    db.commit()
    for j in recalcs: jobs.enqueue(j.id)
    return revision_dict(revision)
@router.post('/{id}/withdraw',status_code=201)
def withdraw(id:int,data:WithdrawInput,db=Depends(get_db),u=Depends(can_write)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    revision,affected,recalcs,paused=datasets.withdraw(db,d,data,u)
    record(db,u.email,'dataset.withdraw',{'id':d.id,'version':revision.version,'operators':data.operators,'invalidated':[j.id for j in affected],'recalcs':[j.id for j in recalcs],'paused_reports':[r.id for r in paused]})
    db.commit()
    for j in recalcs: jobs.enqueue(j.id)
    return revision_dict(revision)
