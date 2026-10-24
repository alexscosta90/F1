"""Use-case layer for dashboard views and endpoint retrieval."""

from collections.abc import Sequence

from f1.dashboard_repository import DashboardRepository, Record


class DashboardService:
    """Coordinates catalog and selected-session reads through a repository."""

    def __init__(self, repository: DashboardRepository) -> None:
        self.repository = repository

    def catalog(self, year: int) -> dict[str, list[Record]]:
        return self.repository.load_catalog(year)

    def session_data(
        self, year: int, session_key: int, endpoints: Sequence[str]
    ) -> dict[str, list[Record]]:
        return {
            endpoint: self.repository.load_endpoint(year, session_key, endpoint)
            for endpoint in endpoints
        }
