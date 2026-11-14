from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset, DatasetRevision
from src.services.business import metadata
from src.services import revisions
from src.utils.serialization import checksum
import math, time
def validate_records(records):
    for index,row in enumerate(records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='': raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
def create(db, data, user=None):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    validate_records(data.records)
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), current_version=1, created_at=time.time())
    db.add(d); db.flush()
    db.add(DatasetRevision(dataset_id=d.id, version=1, action='import', reason='初始导入', records=d.records, checksum=d.checksum, created_by=user.id if user else None, created_at=d.created_at))
    db.flush()
    return d
def correct(db, dataset, data, user):
    validate_records(data.records)
    return revisions.apply(db, dataset, 'correct', data.reason.strip(), data.records, user)
def withdraw(db, dataset, data, user):
    operators=[o.strip() for o in data.operators if o.strip()]
    if not operators: raise HTTPException(422, '请至少指定一名待撤回测时的作业员')
    existing={str(r.get('operator')) for r in dataset.records}
    missing=[o for o in operators if o not in existing]
    if missing: raise HTTPException(404, '批次当前版本中不存在测时人员：'+'、'.join(missing[:5]))
    records=[r for r in dataset.records if str(r.get('operator')) not in operators]
    return revisions.apply(db, dataset, 'withdraw', data.reason.strip(), records, user)
