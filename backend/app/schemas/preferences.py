from pydantic import BaseModel


class PreferencesResponse(BaseModel):
    language: str


class PreferencesUpdateRequest(BaseModel):
    language: str
