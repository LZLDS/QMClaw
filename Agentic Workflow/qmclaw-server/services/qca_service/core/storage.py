# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Storage for QCA Service - HDF5 + SQLite based experiment storage."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

try:
    import h5py
    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False

from .models import ExperimentResult


def _get_db_path(data_dir: Path) -> Path:
    """Get SQLite database path."""
    return data_dir / "index.db"


def _init_db(db_path: Path):
    """Initialize SQLite database schema."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            target TEXT,
            notes TEXT,
            file_path TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_experiment(result: ExperimentResult, data_dir: Path) -> Path:
    """Save experiment result to HDF5 and update SQLite index.

    Args:
        result: ExperimentResult to save
        data_dir: Root data directory

    Returns:
        Path to the saved HDF5 file
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = _get_db_path(data_dir)

    # Initialize DB if needed
    if not db_path.exists():
        _init_db(db_path)

    # Save to HDF5 if available
    file_path = data_dir / f"{result.id}.h5"

    if HAS_H5PY:
        with h5py.File(file_path, "w") as f:
            # Metadata
            f.attrs["id"] = result.id
            f.attrs["type"] = result.type
            f.attrs["timestamp"] = result.timestamp
            f.attrs["status"] = result.status
            f.attrs["target"] = result.target or ""

            # Parameters
            params_grp = f.create_group("params")
            for key, value in result.params.items():
                if isinstance(value, (int, float, str, bool)):
                    params_grp.attrs[key] = value
                else:
                    params_grp.attrs[key] = str(value)

            # Results
            results_grp = f.create_group("results")
            for key, value in result.results.items():
                if isinstance(value, (int, float, str, bool)):
                    results_grp.attrs[key] = value
                else:
                    results_grp.attrs[key] = str(value)

            # Arrays
            arrays_grp = f.create_group("arrays")
            for key, value in result.arrays.items():
                if isinstance(value, (list)):
                    try:
                        import numpy as np
                        arrays_grp.create_dataset(key, data=np.array(value))
                    except Exception:
                        pass

            # Notes
            if result.notes:
                f.attrs["notes"] = result.notes

    else:
        # Fallback: save as JSON
        file_path = data_dir / f"{result.id}.json"
        with open(file_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

    # Update SQLite index
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO experiments (id, type, timestamp, status, target, notes, file_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (result.id, result.type, result.timestamp, result.status, result.target, result.notes, str(file_path)),
    )
    conn.commit()
    conn.close()

    return file_path


def load_experiment(experiment_id: str, data_dir: Path) -> Optional[ExperimentResult]:
    """Load experiment result from HDF5.

    Args:
        experiment_id: Experiment ID
        data_dir: Root data directory

    Returns:
        ExperimentResult or None if not found
    """
    # Try HDF5 first
    h5_path = data_dir / f"{experiment_id}.h5"
    if h5_path.exists() and HAS_H5PY:
        with h5py.File(h5_path, "r") as f:
            params = dict(f["params"].attrs)
            results = dict(f["results"].attrs)
            arrays = {}
            if "arrays" in f:
                for key in f["arrays"]:
                    arrays[key] = f[f"arrays/{key}"][:].tolist()

            return ExperimentResult(
                id=f.attrs["id"],
                type=f.attrs["type"],
                timestamp=f.attrs["timestamp"],
                status=f.attrs["status"],
                target=f.attrs.get("target", "") or None,
                params=params,
                results=results,
                arrays=arrays,
                notes=f.attrs.get("notes", ""),
                file_path=str(h5_path),
            )

    # Fallback: JSON
    json_path = data_dir / f"{experiment_id}.json"
    if json_path.exists():
        with open(json_path) as f:
            return ExperimentResult.from_dict(json.load(f))

    return None


def search_experiments(
    data_dir: Path,
    type: Optional[str] = None,
    last: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Search experiments in SQLite index.

    Args:
        data_dir: Root data directory
        type: Filter by experiment type
        last: Return last N experiments

    Returns:
        List of experiment metadata dicts
    """
    db_path = _get_db_path(data_dir)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT id, type, timestamp, status, target, notes FROM experiments"
    params = []

    if type:
        query += " WHERE type = ?"
        params.append(type)

    query += " ORDER BY timestamp DESC"

    if last:
        query += f" LIMIT {last}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "type": row[1],
            "timestamp": row[2],
            "status": row[3],
            "target": row[4],
            "notes": row[5],
        }
        for row in rows
    ]


def list_arrays(experiment_id: str, data_dir: Path) -> Optional[list[dict[str, Any]]]:
    """List available arrays in an experiment.

    Args:
        experiment_id: Experiment ID
        data_dir: Root data directory

    Returns:
        List of array info dicts or None if experiment not found
    """
    h5_path = data_dir / f"{experiment_id}.h5"
    if not h5_path.exists() or not HAS_H5PY:
        return None

    with h5py.File(h5_path, "r") as f:
        if "arrays" not in f:
            return []

        arrays = []
        for key in f["arrays"]:
            ds = f[f"arrays/{key}"]
            arrays.append({
                "name": key,
                "shape": ds.shape,
                "dtype": str(ds.dtype),
            })
        return arrays


def get_array(
    experiment_id: str,
    array_name: str,
    data_dir: Path,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> Optional[list]:
    """Get array data from experiment.

    Args:
        experiment_id: Experiment ID
        array_name: Name of the array
        data_dir: Root data directory
        start: Start index for slicing
        end: End index for slicing

    Returns:
        Array data as list or None if not found
    """
    h5_path = data_dir / f"{experiment_id}.h5"
    if not h5_path.exists() or not HAS_H5PY:
        return None

    with h5py.File(h5_path, "r") as f:
        if "arrays" not in f or array_name not in f["arrays"]:
            return None

        ds = f[f"arrays/{array_name}"]
        data = ds[:]
        if start is not None or end is not None:
            data = data[start:end]
        return data.tolist()


def get_array_stats(experiment_id: str, array_name: str, data_dir: Path) -> Optional[dict[str, Any]]:
    """Get statistics for an array.

    Args:
        experiment_id: Experiment ID
        array_name: Name of the array
        data_dir: Root data directory

    Returns:
        Statistics dict or None if not found
    """
    h5_path = data_dir / f"{experiment_id}.h5"
    if not h5_path.exists() or not HAS_H5PY:
        return None

    try:
        import numpy as np
    except ImportError:
        return None

    with h5py.File(h5_path, "r") as f:
        if "arrays" not in f or array_name not in f["arrays"]:
            return None

        ds = f[f"arrays/{array_name}"]
        data = ds[:]

        return {
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "mean": float(np.mean(data)),
            "std": float(np.std(data)),
            "count": len(data),
        }
