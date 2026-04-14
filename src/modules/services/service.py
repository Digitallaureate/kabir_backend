import json
import os
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ServicesService:
    def __init__(self):
        self.base_path = Path(__file__).parent / "data"
        self.services_file = self.base_path / "services.json"
        self.forms_dir = self.base_path / "forms"

    def get_services(self) -> Dict[str, Any]:
        """Load, filter, and sort the list of services"""
        try:
            if not self.services_file.exists():
                logger.error(f"Services file not found: {self.services_file}")
                return {"services": []}
            
            with open(self.services_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            services = data.get("services", [])
            
            # Filter: Only return active services
            active_services = [s for s in services if s.get("isActive", False)]
            
            # Sort: Order by ranking (ascending)
            sorted_services = sorted(active_services, key=lambda x: x.get("ranking", 999))
            
            return {"services": sorted_services}
        except Exception as e:
            logger.error(f"Error loading/processing services: {e}")
            return {"services": []}

    def get_service_form(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Load and return a specific service form based on service_id"""
        try:
            form_file = self.forms_dir / f"{service_id}.json"
            
            if not form_file.exists():
                logger.warning(f"Form not found for service_id: {service_id}")
                return None
            
            with open(form_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading form for {service_id}: {e}")
            return None

# Singleton instance
services_service = ServicesService()
