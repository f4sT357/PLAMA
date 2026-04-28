import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from models import PlamaConfig

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, data_dir: str):
        self.config_path = Path(data_dir) / "config.json"
        self.config = PlamaConfig()
        self._load()

    def _load(self):
        abs_path = self.config_path.absolute()
        if not self.config_path.exists():
            logger.info("Config file not found at %s. Creating default.", abs_path)
            self._save()
            return
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                logger.info("Loading config from %s", abs_path)
                data = json.load(f)
                self.config = PlamaConfig(**data)
        except Exception as e:
            logger.error("Failed to load config from %s: %s", abs_path, e)
            self.config = PlamaConfig()

    def _save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config.model_dump(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save config: %s", e)

    def get_config(self) -> PlamaConfig:
        return self.config

    def update_config(self, main_model=None, sub_model=None, bias_model=None, consolidation_model=None):
        if main_model is not None: self.config.main_model = main_model
        if sub_model is not None: self.config.sub_model = sub_model
        if bias_model is not None: self.config.bias_model = bias_model
        if consolidation_model is not None: self.config.consolidation_model = consolidation_model
        
        self.config.last_updated = datetime.now(timezone.utc).isoformat()
        self._save()
        return self.config
