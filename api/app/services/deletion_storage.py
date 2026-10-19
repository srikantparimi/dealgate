"""Resolve the same buckets as uploads and protect surviving object references."""

from sqlalchemy import select

from app.integrations.s3_evidence import _bucket_name as agreement_bucket
from app.integrations.s3_sow import _bucket_name as sow_bucket
from app.models.agreements import StandardAgreement
from app.models.client import Agreement, AgreementFileVersion
from app.models.signed_sow import SignedSowUpload
from app.models.sow import SowVersion
from app.models.sow_upload_job import SowUploadJob


async def key_is_referenced(session, bucket, key):
    if bucket == sow_bucket():
        for model, column in ((SowVersion, SowVersion.file_s3_key),
                              (SignedSowUpload, SignedSowUpload.file_s3_key),
                              (SowUploadJob, SowUploadJob.s3_key)):
            if await session.scalar(select(model.id).where(column == key).limit(1)):
                return True
    if bucket == agreement_bucket():
        if await session.scalar(select(AgreementFileVersion.agreement_id).where(AgreementFileVersion.file_key == key).limit(1)):
            return True
        if await session.scalar(select(Agreement.id).where(Agreement.file_key == key).limit(1)):
            return True
        # S24-AG1: a standard copy is ONE object shared by every client it is attached to. Detaching or
        # deleting its last holder must never queue it: the standard version itself still points at it.
        if await session.scalar(select(StandardAgreement.id).where(StandardAgreement.file_key == key).limit(1)):
            return True
    return False
