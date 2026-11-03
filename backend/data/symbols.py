import os
import json
from datetime import date
from typing import List, Tuple, Optional

class SymbolUniverse:
    def __init__(self, data_dir: str = "data/universe"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def get_current_nifty200(self) -> List[str]:
        """Fetch current Nifty 200 symbols. Fallback to hardcoded list if API fails."""
        try:
            # Attempt to fetch from NSE API or nselib
            # Placeholder for actual API implementation
            return self._fallback_nifty200()
        except Exception as e:
            print(f"API fetch failed: {e}. Using fallback list.")
            return self._fallback_nifty200()

    def _fallback_nifty200(self) -> List[str]:
        """Hardcoded fallback list of Nifty 200 symbols."""
        # Example symbols - replace with actual list
        return ["RELIANCE", "TCS", "HDFCBK", "INFY"]

    def save_snapshot(self, symbols: List[str], as_of: date, source: str) -> None:
        """Save symbol snapshot to dated JSON file."""
        filename = f"nifty200_{as_of.isoformat()}.json"
        filepath = os.path.join(self.data_dir, filename)
        with open(filepath, "w") as f:
            json.dump({
                "symbols": symbols,
                "as_of": as_of.isoformat(),
                "source": source
            }, f)

    def get_snapshot(self, as_of: date) -> List[str]:
        """Load nearest available snapshot for given date."""
        snapshots = self.list_snapshots()
        if not snapshots:
            raise ValueError("No snapshots available")
        # Find closest date (simplified: pick first earlier or later)
        # For production: implement proper date proximity logic
        available_dates = [d for d, _ in snapshots]
        for d in available_dates:
            if d <= as_of:
                closest_date = d
                break
        else:
            closest_date = available_dates[-1]
        # Load snapshot for closest_date
        filepath = os.path.join(self.data_dir, f"nifty200_{closest_date.isoformat()}.json")
        with open(filepath, "r") as f:
            data = json.load(f)
        return data["symbols"]

    def list_snapshots(self) -> List[Tuple[date, int]]:
        """List available snapshots with date and symbol count."""
        snapshots = []
        for filename in os.listdir(self.data_dir):
            if filename.startswith("nifty200_") and filename.endswith(".json"):
                date_str = filename[len("nifty200_"):-5]
                try:
                    as_of = date.fromisoformat(date_str)
                except ValueError:
                    continue
                filepath = os.path.join(self.data_dir, filename)
                with open(filepath, "r") as f:
                    data = json.load(f)
                snapshots.append((as_of, len(data["symbols"])))
        return sorted(snapshots, key=lambda x: x[0], reverse=True)

    def filter_by_liquidity(self, symbols: List[str], bars: List[dict], min_value: float) -> List[str]:
        """Filter symbols based on liquidity (avg daily value)."""
        # Placeholder: calculate avg value per symbol from bars
        # This is a simplified implementation
        return symbols[:10]  # Replace with actual logic

    def filter_by_coverage(self, symbols: List[str], bars: List[dict], min_coverage: float) -> List[str]:
        """Filter symbols based on data coverage percentage."""
        # Placeholder: calculate coverage per symbol from bars
        # This is a simplified implementation
        return symbols[:15]  # Replace with actual logic
