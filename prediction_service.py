"""Inference only: never train or replace the reviewed repository model."""
import hashlib
import math
from pathlib import Path
from threading import Lock

MODEL_SHA256 = '10d48fa23b05da63acea8133f1163ef73841b017e1346e4d395c758ffe6bc68f'
NUMERIC = {
    'Coût_production/ha': ('Dépenses par hectare (FCFA)', 0, 1000000000),
    'Age_verger': ('Âge des cacaoyers (années)', 0, 150),
}
LABELS = {
    'Région': 'Région', 'Pluviometrie': 'Quantité de pluie', 'Sexe': 'Sexe du producteur',
    'Niveau_education': 'Niveau scolaire', 'Competences': 'Lecture et écriture',
    'Engrais chimique': 'Utilisation d’engrais chimique', 'Agroforesterie': 'Autres arbres dans la plantation',
    'fumier/ compost': 'Fumier ou compost', 'Herbicide': 'Produit contre les mauvaises herbes',
    'Insecticide': 'Produit contre les insectes', 'Fongicide': 'Produit contre les champignons',
    'Maladie': 'Maladie observée',
}


class ModelUnavailable(RuntimeError):
    pass


class Predictor:
    def __init__(self, path):
        self.path = Path(path)
        self.model = None
        self.lock = Lock()

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            try:
                # Pickle is executable: only load the known, trusted artifact, never an upload.
                if hashlib.sha256(self.path.read_bytes()).hexdigest() != MODEL_SHA256:
                    raise RuntimeError('Unreviewed model artifact')
                import joblib
                model = joblib.load(self.path)
                prep = model.named_steps['prep']
                columns = list(prep.feature_names_in_)
                if set(columns) != set(NUMERIC) | set(LABELS):
                    raise RuntimeError('Unexpected model schema')
                categorical_columns = list(next(cols for name, _, cols in prep.transformers_ if name == 'cat'))
                encoder = prep.named_transformers_['cat'].named_steps['onehot']
                categories = {name: [str(v) for v in values] for name, values in zip(categorical_columns, encoder.categories_)}
                if set(categories) != set(LABELS):
                    raise RuntimeError('Unexpected categorical schema')
                model.named_steps['model'].set_params(n_jobs=1)
                self.columns, self.categories, self.model = columns, categories, model
            except Exception as exc:
                raise ModelUnavailable('Le calcul est indisponible. Réessayez plus tard.') from exc

    def schema(self):
        self.load()
        fields = []
        for name in self.columns:
            if name in NUMERIC:
                label, low, high = NUMERIC[name]
                fields.append(dict(name=name, label=label, type='number', minimum=low, maximum=high))
            else:
                fields.append(dict(name=name, label=LABELS[name], type='select', options=self.categories[name]))
        return dict(fields=fields, model_version=MODEL_SHA256, unit='t/ha')

    def predict(self, data):
        self.load()
        inputs = data.get('inputs')
        if not isinstance(inputs, dict) or set(inputs) != set(self.columns):
            raise ValueError('Complétez tous les champs du formulaire.')
        clean = {}
        for name in self.columns:
            value = inputs[name]
            if name in NUMERIC:
                label, low, high = NUMERIC[name]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                    raise ValueError(f'{label} doit être un nombre entre {low} et {high}.')
            elif not isinstance(value, str) or value not in self.categories[name]:
                raise ValueError(f'Choisissez une valeur reconnue pour {LABELS[name]}.')
            clean[name] = value
        area = data.get('area_ha')
        if isinstance(area, bool) or not isinstance(area, (int, float)) or not math.isfinite(area) or not 0.01 <= area <= 100000:
            raise ValueError('La surface doit être comprise entre 0,01 et 100 000 ha.')
        try:
            import pandas as pd
            value = float(self.model.predict(pd.DataFrame([clean], columns=self.columns))[0])
            if not math.isfinite(value) or value < 0:
                raise RuntimeError('Invalid model result')
        except Exception as exc:
            raise ModelUnavailable('Le calcul a échoué. Aucun résultat n’a été enregistré.') from exc
        return dict(inputs=clean, area_ha=area, productivity_t_ha=value,
                    estimated_total_kg=value*1000*area, model_version=MODEL_SHA256)
