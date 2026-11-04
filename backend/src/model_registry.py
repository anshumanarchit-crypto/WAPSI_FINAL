"""
WAPSI Model Registry & Artifact Management.
Manages versioning, metadata manifests, serialization, and deployment promotion
for causal recovery models.
"""

from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import json
from datetime import datetime, timezone
import joblib

from src.t_learner import WAPSIUpliftModel
from src.x_learner import WAPSIXLearner


class ModelRegistry:
    """
    Local filesystem model registry managing versioned WAPSI causal models.
    Supports both T-Learner and X-Learner model architectures.
    """

    def __init__(self, registry_dir: str = "models"):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.registry_dir / "manifest.json"
        self._init_manifest()

    def _init_manifest(self):
        if not self.manifest_path.exists():
            initial_manifest = {
                "active_production_version": None,
                "registered_models": []
            }
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(initial_manifest, f, indent=2)

    def _read_manifest(self) -> Dict[str, Any]:
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_manifest(self, manifest: Dict[str, Any]):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def register_model(
        self,
        model: Union[WAPSIUpliftModel, WAPSIXLearner, Any],
        model_name: str = "wapsi_t_learner",
        version: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        set_as_production: bool = False
    ) -> str:
        """
        Saves model artifact and records registration entry in the manifest.
        """
        manifest = self._read_manifest()
        
        if version is None:
            # Auto-increment version
            count = len([m for m in manifest["registered_models"] if m["model_name"] == model_name])
            version = f"v{count + 1}.0.0"

        filename = f"{model_name}_{version}.joblib"
        artifact_path = self.registry_dir / filename
        
        # Save model via joblib
        model.save(artifact_path)
        
        # Record metadata
        meta = model.get_metadata()
        entry = {
            "model_name": model_name,
            "version": version,
            "filename": filename,
            "artifact_path": str(artifact_path),
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "model_type": meta.get("model_type", type(model).__name__),
            "training_rows": meta.get("training_rows", 0),
            "random_seed": meta.get("random_seed", 42),
            "metrics": metrics or meta.get("validation_metrics", {}),
            "is_production": set_as_production
        }

        if set_as_production:
            manifest["active_production_version"] = version
            for m in manifest["registered_models"]:
                if m["model_name"] == model_name:
                    m["is_production"] = False

        manifest["registered_models"].append(entry)
        self._save_manifest(manifest)

        return str(artifact_path)

    def get_model(
        self,
        model_name: str = "wapsi_t_learner",
        version: str = "latest"
    ) -> Any:
        """
        Retrieves and deserializes a model by version or 'latest' / 'production'.
        """
        manifest = self._read_manifest()
        matching = [m for m in manifest["registered_models"] if m["model_name"] == model_name]
        
        if not matching:
            raise ValueError(f"No models registered under name '{model_name}'.")

        if version == "production":
            prod_v = manifest.get("active_production_version")
            if not prod_v:
                entry = matching[-1]
            else:
                entry = next((m for m in matching if m["version"] == prod_v), matching[-1])
        elif version == "latest":
            entry = matching[-1]
        else:
            entry = next((m for m in matching if m["version"] == version), None)
            if entry is None:
                raise ValueError(f"Model version '{version}' not found for '{model_name}'.")

        artifact_path = Path(entry["artifact_path"])
        if not artifact_path.exists():
            raise FileNotFoundError(f"Model file not found at: {artifact_path}")
        return joblib.load(artifact_path)

    def list_models(self) -> List[Dict[str, Any]]:
        """Lists all registered models in the registry manifest."""
        manifest = self._read_manifest()
        return list(manifest["registered_models"])

    def promote_to_production(self, model_name: str, version: str):
        """Sets a specified model version as the active production model."""
        manifest = self._read_manifest()
        found = False
        for m in manifest["registered_models"]:
            if m["model_name"] == model_name and m["version"] == version:
                m["is_production"] = True
                found = True
            elif m["model_name"] == model_name:
                m["is_production"] = False

        if not found:
            raise ValueError(f"Model '{model_name}' version '{version}' not found in registry.")

        manifest["active_production_version"] = version
        self._save_manifest(manifest)
