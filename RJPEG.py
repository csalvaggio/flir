import io
import json
import os
import shutil
import subprocess
from typing import Any, Optional

import numpy as np
import PIL
import PIL.Image


class RJPEG(object):

    def __init__(self, path: str,
                 calibration_coefficients: np.ndarray = None) -> None:

        if shutil.which("exiftool") is None:
            msg = f"exiftool not found on PATH. Please install ExifTool "
            msg += f"and try again."
            raise RuntimeError(msg)

        if not os.path.exists(path):
            msg = f"The RJPEG path provided does not exist: {path}"
            raise FileNotFoundError(msg)
        if not os.path.isfile(path):
            msg = f"Expected a file, but got a directory: {path}"
            raise IsADirectoryError(msg)
        if not os.access(path, os.R_OK):
            msg = f"The RJPEG path provided is not readable: {path}"
            raise PermissionError(msg)

        self._metadata: dict[str, Any] = self._read_metadata(path)
        self._raw_counts: np.ndarray = \
            self._extract_embedded_raw_thermal_image(path)
        self._radiance: Optional[np.ndarray] = None

        if calibration_coefficients is not None:
            self._compute_radiance_using_calibration_coefficients(
                calibration_coefficients
            )
        else:
            self._compute_radiance_using_embedded_flir_approach()

    # ---------- Properties ----------
    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self._raw_counts.shape[:2])

    @property
    def size(self) -> int:
        return int(self._raw_counts.size)
    
    @property
    def dtype(self) -> np.dtype:
        return self._raw_counts.dtype

    # ---------- Metadata ----------
    @staticmethod
    def _read_metadata(path: str) -> dict[str, Any]:
        cmd = ["exiftool", "-j", "-n", path]
        result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True)
        metadata = json.loads(result.stdout)[0]
        return metadata

    def metadata(self, key: Optional[str] = None) -> Any:
        if key is None:
            return dict(self._metadata)
        try:
            return self._metadata[key]
        except KeyError:
            msg = f"Provided key not found in metadata: {key}"
            raise KeyError(msg) from None

    # ---------- Raw extraction ----------
    @staticmethod
    def _extract_embedded_raw_thermal_image(path: str) -> np.ndarray:
        cmd = ["exiftool", "-b", "-RawThermalImage", path]
        result = subprocess.run(
                    cmd,
                    capture_output=True,
                    check=True)
        blob = result.stdout

        raw = PIL.Image.open(io.BytesIO(blob))
        img = np.array(raw)
        if img.dtype != np.uint16:
            img = img.astype(np.uint16, copy=False)

        return img

    @property
    def raw_counts(self) -> np.ndarray:
        return self._raw_counts

    def write_raw_counts_to_tiff(self, path: str) -> None:
        PIL.Image.fromarray(self._raw_counts).save(path)

    # ---------- Radiance computation ----------
    def _compute_radiance_using_embedded_flir_approach(self) -> None:
        """
          Compute sensor-reaching radiance from raw counts according to

                            R1
              L = ---------------------- - F
                   R2 * (raw_count + O)

        """
        R1 = float(self._metadata["PlanckR1"])
        R2 = float(self._metadata["PlanckR2"])
        O  = float(self._metadata["PlanckO"])
        F  = float(self._metadata["PlanckF"])

        raw_counts = (2**16 - 1) - self._raw_counts

        denominator = \
            (R2 * (raw_counts.astype(np.float32) + O)).astype(np.float32)
        bad_pixels = denominator <= 0
        denominator[bad_pixels] = np.nan
        L = (R1 / denominator - F)

        self._radiance = L.astype(np.float32, copy = False)

    def _compute_radiance_using_calibration_coefficients(self) -> None:
        pass

    @property
    def radiance(self) -> Optional[np.ndarray]:
        return self._radiance

    def write_radiance_to_tiff(self, path: str) -> None:
        PIL.Image.fromarray(self._radiance, mode="F").save(path)



if __name__ == '__main__':

    import argparse
    import flir

    description = "Test harness to read in and create a FLIR RJPEG object"
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "path",
        help="Path to a FLIR radiometric JPEG"
    )
    ap.add_argument(
        "-r",
        "--rawpath",
        default=None,
        help="Output path to TIFF to store raw counts (uint16)",
    )
    ap.add_argument(
        "-l",
        "--radpath",
        default=None,
        help="Output path to TIFF to store radiance (float32)",
    )
    args = ap.parse_args()

    src = RJPEG(args.path)

    # Access all metadata items
    for key, value in src.metadata().items():
        print(f"{key}: {value}")

    # Access a single metadata item
    print(f"ImageWidth: {src.metadata('ImageWidth')}")

    # Report back the size and type of the embedded raw image
    rows, cols = src.shape
    size = src.size
    dtype = src.dtype
    print(f"{cols} x {rows} [{size}] ({dtype})")

    # Write raw counts to TIFF (uint16)
    if args.rawpath:
        print(f"Writing raw counts to {args.rawpath}")
        src.write_raw_counts_to_tiff(args.rawpath)

    # Write radiance to TIFF (float32)
    if args.radpath:
        if src.radiance is None:
            print(f"RJPEG object contains no radiance, ignoring write request")
        else:
            print(f"Writing radiance to {args.radpath}")
            src.write_radiance_to_tiff(args.radpath)
