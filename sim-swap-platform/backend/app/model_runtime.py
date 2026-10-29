"""Native JSON artifacts only; never unpickle an untrusted model."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .features import VERSION, NAMES, vector


class ModelRuntime:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.cache = {}

    def manifest(self, model_id):
        if not model_id.replace('-', '').replace('_', '').isalnum() or len(model_id) > 80:
            raise ValueError('Invalid model identifier')
        folder = (self.root / model_id).resolve()
        if folder.parent != self.root:
            raise ValueError('Model path escape')
        manifest = json.loads((folder / 'manifest.json').read_text())
        if manifest['feature_version'] != VERSION or manifest['feature_names'] != NAMES:
            raise ValueError('Model feature schema is incompatible')
        artifact = folder / 'model.json'
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Model artifact integrity check failed')
        return manifest, artifact

    def score(self, model_id, features):
        manifest, artifact = self.manifest(model_id)
        key = (model_id, manifest['sha256'])
        if key not in self.cache:
            if manifest['algorithm'] == 'logistic':
                self.cache[key] = json.loads(artifact.read_text())
            elif manifest['algorithm'] == 'xgboost':
                import xgboost as xgb
                model = xgb.Booster()
                model.load_model(str(artifact))
                self.cache[key] = model
            else:
                raise ValueError('Unsupported model algorithm')
        x = vector(features)
        if manifest['algorithm'] == 'logistic':
            model = self.cache[key]
            standardized = (x - np.array(model['mean'])) / np.array(model['scale'])
            logit = float((standardized @ np.array(model['coefficients']) + model['intercept']).item())
            score = float(1 / (1 + np.exp(-np.clip(logit, -50, 50))))
        else:
            import xgboost as xgb
            score = float(self.cache[key].predict(xgb.DMatrix(x, feature_names=NAMES))[0])
        return score, manifest
