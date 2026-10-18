"""Download the public UCI Beijing Multi-Site Air Quality dataset."""
from pathlib import Path
from backend.ml.data_utils import download_uci_dataset

if __name__ == "__main__":
    location = download_uci_dataset(force=True)
    count = len(list(Path(location).rglob("PRSA_Data_*.csv")))
    print(f"Dataset downloaded and extracted to: {location}")
    print(f"Station CSV files found: {count}")
