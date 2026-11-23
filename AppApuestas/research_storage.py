"""Almacenamiento histórico opcional de análisis mediante Supabase REST.

Solo persiste cuando SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY están configuradas
en el servidor. No hace llamadas a Supabase al importar el módulo.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests


class ResearchStorageError(RuntimeError):
    pass


class ResearchStorage:
    def __init__(self, timeout: float = 12.0):
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.table = os.getenv("SUPABASE_RESEARCH_TABLE", "research_snapshots").strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        if not self.url or not self.key:
            return False
        parsed = urlparse(self.url)
        return parsed.scheme == "https" and bool(parsed.netloc)

    def status(self) -> dict[str, Any]:
        return {
            "proveedor": "Supabase REST",
            "configurado": self.configured,
            "tabla": self.table,
            "modo": "servidor privado; usa service-role key" if self.configured else "desactivado",
            "nota": (
                "El almacenamiento no se usa hasta configurar SUPABASE_URL y "
                "SUPABASE_SERVICE_ROLE_KEY en Render. No se ha seleccionado ni modificado una base existente."
            ),
        }

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": "Bearer " + self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def save_snapshot(
        self,
        provider: str,
        match_id: str,
        snapshot_type: str,
        payload: dict[str, Any],
        source_timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"guardado": False, "motivo": "SUPABASE_NOT_CONFIGURED"}
        if not provider or not match_id or not snapshot_type:
            raise ValueError("provider, match_id y snapshot_type son obligatorios.")
        snapshot_date = datetime.now(timezone.utc).date().isoformat()
        row = {
            "provider": provider[:40],
            "match_id": str(match_id)[:100],
            "snapshot_type": snapshot_type[:60],
            "snapshot_date": snapshot_date,
            "source_timestamp": source_timestamp,
            "model_version": os.getenv("APP_MODEL_VERSION", "research-1"),
            "payload": payload,
        }
        url = f"{self.url}/rest/v1/{self.table}"
        try:
            response = requests.post(
                url,
                params={"on_conflict": "provider,match_id,snapshot_type,snapshot_date"},
                headers=self._headers(),
                json=row,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ResearchStorageError("No se pudo guardar el snapshot en Supabase: " + str(exc)) from exc
        if response.status_code >= 400:
            raise ResearchStorageError(
                f"Supabase rechazó el snapshot (HTTP {response.status_code}). Revisa la migración y las variables del servicio."
            )
        return {"guardado": True, "provider": row["provider"], "match_id": row["match_id"], "snapshot_date": snapshot_date}

    def history(self, provider: str, match_id: str, limit: int = 30) -> list[dict[str, Any]]:
        if not self.configured:
            raise ResearchStorageError("El almacenamiento Supabase no está configurado.")
        safe_limit = max(1, min(100, int(limit)))
        url = f"{self.url}/rest/v1/{self.table}"
        try:
            response = requests.get(
                url,
                params={
                    "select": "provider,match_id,snapshot_type,snapshot_date,source_timestamp,model_version,payload",
                    "provider": "eq." + provider,
                    "match_id": "eq." + str(match_id),
                    "order": "snapshot_date.desc",
                    "limit": str(safe_limit),
                },
                headers={
                    "apikey": self.key,
                    "Authorization": "Bearer " + self.key,
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ResearchStorageError("No se pudo consultar el historial en Supabase: " + str(exc)) from exc
        if response.status_code >= 400:
            raise ResearchStorageError(f"Supabase rechazó la consulta de historial (HTTP {response.status_code}).")
        try:
            data = response.json()
        except ValueError as exc:
            raise ResearchStorageError("Supabase devolvió JSON no válido.") from exc
        return data if isinstance(data, list) else []
