from pydantic import Field

from services.core.domain import Model, ProjectType, ProviderCapabilities, ProviderHealth


class ProjectCreate(Model):
    name: str = Field(min_length=1)
    type: ProjectType = ProjectType.APARTMENT
    location_note: str | None = None


class StylePackCreate(Model):
    name: str = Field(min_length=1)
    project_id: str | None = None
    palette: list[str] = Field(default_factory=list)


class FinalizeRequest(Model):
    provider_id: str | None = None
    image_size: str = '2K'
    confirm_high_cost: bool = False


class ProviderInfo(Model):
    id: str
    capabilities: ProviderCapabilities
    health: ProviderHealth


class HealthResponse(Model):
    status: str = 'ok'
    providers: list[ProviderInfo]
