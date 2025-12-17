import pandas as pd
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from src.indicators import IndicatorEngine

class MLEngine:
    def __init__(self, model_path="ml_model.joblib"):
        self.model_path = model_path
        self.model = None
        self.load_model()

    def prepare_features(self, df: pd.DataFrame):
        """
        Generates features for ML.
        """
        # Ensure indicators exist
        df = IndicatorEngine.add_indicators(df)

        # Features: RSI, MACD lines, Close vs Open, Volume Change
        # We need to drop NaNs created by indicators
        df = df.copy()

        # Create Target: 1 if Next Close > Current Close (Up), 0 otherwise
        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)

        # Select Feature Columns
        # We assume standard indicator names from pandas_ta defaults
        feature_cols = ['RSI_14', 'volume']

        # Add MACD cols if they exist (names vary)
        for col in df.columns:
            if 'MACD' in col or 'BBL' in col or 'BBU' in col:
                feature_cols.append(col)

        # Drop rows with NaN (indicators or target)
        df_clean = df.dropna()

        return df_clean, feature_cols

    def train_model(self, df: pd.DataFrame):
        """
        Trains a RandomForest model.
        """
        data, feature_cols = self.prepare_features(df)

        if data.empty:
            print("Not enough data to train ML model.")
            return

        X = data[feature_cols]
        y = data['target']

        # Split (not strictly needed if we just want to train on all history for live usage,
        # but good for validation metrics if we were doing that)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

        self.model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        self.model.fit(X_train, y_train)

        self.feature_cols = feature_cols # Store in memory

        # Save
        joblib.dump(self.model, self.model_path)
        joblib.dump(feature_cols, self.model_path + "_features")

        print("ML Model trained and saved.")
        return self.model.score(X_test, y_test)

    def load_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                self.feature_cols = joblib.load(self.model_path + "_features")
            except:
                print("Failed to load ML model.")
                self.model = None

    def predict_probability(self, current_candle_df: pd.DataFrame):
        """
        Predicts probability of UP move for the *latest* candle state.
        """
        if not self.model:
            return 0.5

        # Prepare features exactly as training
        # We need to ensure the DF has indicators calculated
        df = IndicatorEngine.add_indicators(current_candle_df)

        # We only need the last row
        last_row = df.iloc[[-1]][self.feature_cols]

        # Handle missing cols if any (fill 0 or error)
        last_row = last_row.fillna(0)

        try:
            # Predict Proba returns [prob_class_0, prob_class_1]
            prob = self.model.predict_proba(last_row)[0][1]
            return prob
        except Exception as e:
            print(f"Prediction Error: {e}")
            return 0.5
