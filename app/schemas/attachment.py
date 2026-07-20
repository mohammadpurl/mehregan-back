from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttachmentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    file_name: str = Field(serialization_alias="fileName")
    url: str
    file_url: str | None = Field(None, serialization_alias="fileUrl")
    download_url: str | None = Field(None, serialization_alias="downloadUrl")
    preview_url: str | None = Field(None, serialization_alias="previewUrl")
    preview_file_url: str | None = Field(None, serialization_alias="previewFileUrl")
    content_type: str | None = Field(None, serialization_alias="contentType")
    uploaded_at: datetime | None = Field(None, serialization_alias="uploadedAt")
