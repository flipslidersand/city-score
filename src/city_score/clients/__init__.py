"""外部データソース向け API クライアント."""

from city_score.clients.estat_client import EstatApiClient, EstatApiError

__all__ = ["EstatApiClient", "EstatApiError"]
