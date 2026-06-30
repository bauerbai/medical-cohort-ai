from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import auc, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from engine.base import AnalysisResult, AnalysisValidationError, BaseAnalysis, register_analysis


@register_analysis("ml.risk_prediction")
class DiseaseRiskPrediction(BaseAnalysis):
    analysis_id: ClassVar[str] = "ml.risk_prediction"
    title: ClassVar[str] = "Disease risk prediction"
    description: ClassVar[str] = "Gradient boosting risk model with ROC and decision curve data."

    def validate_data(self) -> None:
        outcome = self.parameters.get("outcome_col")
        features = self.parameters.get("features", [])
        self.required_columns = [outcome, *features]
        super().validate_data()
        if self.data[outcome].nunique(dropna=True) != 2:
            raise AnalysisValidationError("Binary outcome with both classes is required")

    def _execute_sync(self) -> AnalysisResult:
        outcome = self.parameters["outcome_col"]
        features = self.parameters["features"]
        df = self.data[[outcome, *features]].dropna(subset=[outcome]).copy()
        x = pd.get_dummies(df[features], drop_first=True)
        y = df[outcome].astype(int)
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=float(self.parameters.get("test_size", 0.25)), random_state=42, stratify=y)
        model = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=42)),
        ])
        model.fit(x_train, y_train)
        prob = model.predict_proba(x_test)[:, 1]
        fpr, tpr, thresholds = roc_curve(y_test, prob)
        dca = self._decision_curve(y_test.to_numpy(), prob)
        result = self._base_result(len(df))
        result.estimates = [{"auc": float(roc_auc_score(y_test, prob)), "n_train": int(len(y_train)), "n_test": int(len(y_test))}]
        result.plots = {
            "roc_plotly": {"data": [{"type": "scatter", "mode": "lines", "x": fpr.tolist(), "y": tpr.tolist(), "name": "Model ROC"}], "layout": {"title": "ROC Curve", "xaxis": {"title": "1 - Specificity"}, "yaxis": {"title": "Sensitivity"}}},
            "dca_plotly": dca,
        }
        result.diagnostics = {"thresholds": thresholds.tolist()}
        return result

    def _decision_curve(self, y_true: np.ndarray, prob: np.ndarray) -> dict[str, Any]:
        thresholds = np.linspace(0.05, 0.8, 16)
        n = len(y_true)
        net_benefits = []
        prevalence = y_true.mean()
        for threshold in thresholds:
            pred = prob >= threshold
            tp = ((pred == 1) & (y_true == 1)).sum()
            fp = ((pred == 1) & (y_true == 0)).sum()
            nb = tp / n - fp / n * threshold / (1 - threshold)
            net_benefits.append(float(nb))
        treat_all = [float(prevalence - (1 - prevalence) * t / (1 - t)) for t in thresholds]
        return {"data": [{"type": "scatter", "mode": "lines", "x": thresholds.tolist(), "y": net_benefits, "name": "Model"}, {"type": "scatter", "mode": "lines", "x": thresholds.tolist(), "y": treat_all, "name": "Treat all"}], "layout": {"title": "Decision Curve Analysis", "xaxis": {"title": "Risk threshold"}, "yaxis": {"title": "Net benefit"}}}

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "estimates": result.estimates, "plots": result.plots}


@register_analysis("ml.kmeans_subtyping")
class KMeansClinicalSubtyping(BaseAnalysis):
    analysis_id: ClassVar[str] = "ml.kmeans_subtyping"
    title: ClassVar[str] = "K-Means clinical subtyping"
    description: ClassVar[str] = "Unsupervised clinical subtype discovery using standardized numeric features."

    def validate_data(self) -> None:
        features = self.parameters.get("features", [])
        self.required_columns = features
        super().validate_data()
        if len(features) < 2:
            raise AnalysisValidationError("At least two features are recommended for clustering")

    def _execute_sync(self) -> AnalysisResult:
        features = self.parameters["features"]
        k = int(self.parameters.get("n_clusters", 3))
        df = self.data[features].copy()
        x = df.apply(pd.to_numeric, errors="coerce")
        pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("kmeans", KMeans(n_clusters=k, n_init="auto", random_state=42))])
        labels = pipeline.fit_predict(x)
        centers_scaled = pipeline.named_steps["kmeans"].cluster_centers_
        centers = pipeline.named_steps["scaler"].inverse_transform(centers_scaled)
        result = self._base_result(len(df))
        result.estimates = [{"n_clusters": k, "inertia": float(pipeline.named_steps["kmeans"].inertia_)}]
        result.tables = {"cluster_sizes": pd.Series(labels).value_counts().sort_index().astype(int).to_dict(), "cluster_centers": [dict(zip(features, row.astype(float).tolist())) for row in centers]}
        result.plots = {"cluster_assignment": labels.astype(int).tolist()}
        return result

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "estimates": result.estimates, "tables": result.tables}
