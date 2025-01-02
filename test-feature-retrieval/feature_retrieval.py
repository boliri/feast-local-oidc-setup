import json
from datetime import datetime

import pandas as pd
from feast import FeatureStore


def run():
    print("Initializing Feature Store...")
    fs = FeatureStore(repo_path=".")
    print("Feature Store initialized\n")

    try:
        print("Fetching historical features... (remember to run `docker-compose up --build register-features` first!)")
        offline_resp = fs.get_historical_features(
            features=[
                "driver_hourly_stats:conv_rate",
                "driver_hourly_stats:acc_rate",
                "driver_hourly_stats:avg_daily_trips",
            ],
            entity_df=pd.DataFrame.from_dict({
                # entity's join key -> entity values
                "driver_id": [1001, 1002, 1003],
                # "event_timestamp" (reserved key) -> timestamps
                "event_timestamp": [
                    datetime(2021, 4, 12, 10, 59, 42),
                    datetime(2021, 4, 12, 8, 12, 10),
                    datetime(2021, 4, 12, 16, 40, 26),
                ],
                # (optional) label name -> label values. Feast does not process these
                "label_driver_reported_satisfaction": [1, 5, 3],
                # values we're using for an on-demand transformation
                "val_to_add": [1, 2, 3],
                "val_to_add_2": [10, 20, 30],
            })
        )
        historical_features = offline_resp.to_df()
    except Exception as e:
        print(f"Failed to fetch historical features: {e}")
    else:
        print("---- HISTORICAL FEATURES ----")
        print(historical_features)
        print()

    try:
        print("Fetching online features... (remember to run `docker-compose up --build materialize-features` first!)")
        online_resp = fs.get_online_features(features=[
                "driver_hourly_stats:conv_rate",
                "driver_hourly_stats:acc_rate",
                "driver_hourly_stats:avg_daily_trips",
            ],
            entity_rows=[
                # {join_key: entity_value}
                {"driver_id": 1004},
                {"driver_id": 1005},
            ],
        )
    except Exception as e:
        print(f"Failed to fetch online features: {e}")
    else:
        online_features = online_resp.to_dict()

        print("---- ONLINE FEATURES ----")
        print(json.dumps(online_features, indent=4))
        print()

    print("Done!")

if __name__ == "__main__":
    run()
