import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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

        self._rgb: np.ndarray = self._extract_embedded_rgb_image(path)

        self._raw_counts: np.ndarray = \
            self._extract_embedded_raw_thermal_image(path)

        if calibration_coefficients is not None:
            self._compute_radiance_using_calibration_coefficients(
                calibration_coefficients
            )
        else:
            self._compute_radiance_using_embedded_flir_approach()

    # ---------- Properties ----------
    @property
    def shape(self) -> Optional[tuple[int, int]]:
        if self._raw_counts is not None:
            return tuple(self._raw_counts.shape[:2])
        else:
            return None

    @property
    def size(self) -> Optional[int]:
        if self._raw_counts is not None:
            return int(self._raw_counts.size)
        else:
            return None
    
    @property
    def dtype(self) -> Optional[np.dtype]:
        if self._raw_counts is not None:
            return self._raw_counts.dtype
        else:
            return None

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

    # ---------- RGB extraction ----------
    @staticmethod
    def _extract_embedded_rgb_image(path: str) -> Optional[np.ndarray]:
        cmd = ["exiftool", "-b", "-EmbeddedImage", path]
        result = subprocess.run(
                    cmd,
                    capture_output=True,
                    check=True)
        blob = result.stdout

        if not blob:
            return None
        else:
            raw = PIL.Image.open(io.BytesIO(blob))
            img = np.array(raw)
            if img.dtype != np.uint8:
                img = img.astype(np.uint8, copy=False)

            return img

    @property
    def rgb(self) -> Optional[np.ndarray]:
        return self._rgb

    def write_rgb(self, path: str) -> None:
        if src._rgb is not None:
            # Make sure the path extension is indicative of a TIFF format file,
            # if it is not, remove the current extension and replace it with one
            # that is
            p = Path(path)
            ext = p.suffix.lower()
            if ext not in (".tif", ".tiff"):
                p = p.with_suffix(".tif")
            PIL.Image.fromarray(self._rgb).save(p, format="TIFF")
        else:
            msg = f"WARNING: RJPEG object contains no RGB data, "
            msg += f"ignoring write request"
            print(msg)

    # ---------- Raw extraction ----------
    @staticmethod
    def _extract_embedded_raw_thermal_image(path: str) -> Optional[np.ndarray]:
        cmd = ["exiftool", "-b", "-RawThermalImage", path]
        result = subprocess.run(
                    cmd,
                    capture_output=True,
                    check=True)
        blob = result.stdout

        if not blob:
            return None
        else:
            raw = PIL.Image.open(io.BytesIO(blob))
            img = np.array(raw)
            if img.dtype != np.uint16:
                img = img.astype(np.uint16, copy=False)

            byte_order = img.dtype.byteorder
            needs_swapped = \
                    (byte_order == '>' and sys.byteorder == 'little') or \
                (byte_order == '<' and sys.byteorder == 'big')
            if needs_swapped:
                img = img.byteswap().newbyteorder()

            return img

    @property
    def raw_counts(self) -> Optional[np.ndarray]:
        return self._raw_counts

    def write_raw_counts(self, path: str) -> None:
        if src._raw_counts is not None:
            # Make sure the path extension is indicative of a TIFF format file,
            # if it is not, remove the current extension and replace it with one
            # that is
            p = Path(path)
            ext = p.suffix.lower()
            if ext not in (".tif", ".tiff"):
                p = p.with_suffix(".tif")
            PIL.Image.fromarray(self._raw_counts).save(p, format="TIFF")
        else:
            msg = f"WARNING: RJPEG object contains no raw counts, "
            msg += f"ignoring write request"
            print(msg)

    # ---------- Radiance computation ----------
    def _compute_radiance_using_embedded_flir_approach(self) -> None:
        """
          Compute sensor-reaching radiance from raw counts according to

                            R1
              L = ---------------------- - F
                   R2 * (raw_count + O)

        """
        if self._raw_counts is not None:
            R1 = float(self._metadata["PlanckR1"])
            R2 = float(self._metadata["PlanckR2"])
            O  = float(self._metadata["PlanckO"])
            F  = float(self._metadata["PlanckF"])

            raw_counts = (2**16 - 1) - O - self._raw_counts

            denominator = \
                (R2 * (raw_counts.astype(np.float32) + O)).astype(np.float32)
            bad_pixels = denominator <= 0
            denominator[bad_pixels] = np.nan
            L = (R1 / denominator - F)

            self._radiance = L.astype(np.float32, copy = False)
        else:
            self._radiance = None

    def _compute_radiance_using_calibration_coefficients(self) -> None:
        self._radiance = None

    @property
    def radiance(self) -> Optional[np.ndarray]:
        return self._radiance

    def write_radiance(self, path: str) -> None:
        if src._radiance is not None:
            # Make sure the path extension is indicative of a TIFF format file,
            # if it is not, remove the current extension and replace it with one
            # that is
            p = Path(path)
            ext = p.suffix.lower()
            if ext not in (".tif", ".tiff"):
                p = p.with_suffix(".tif")
            PIL.Image.fromarray(self._radiance, mode="F").save(p, format="TIFF")
        else:
            msg = f"WARNING: RJPEG object contains no radiance, "
            msg += f"ignoring write request"
            print(msg)



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
        help="Output path to store raw counts (uint16) " \
             "[NOTE: Must be TIFF format]"
    )
    ap.add_argument(
        "-l",
        "--radpath",
        default=None,
        help="Output path to store radiance (float32) " + \
             "[NOTE: Must be TIFF format]"
    )
    ap.add_argument(
        "-v",
        "--rgbpath",
        default=None,
        help="Output path to store RGB (uint8) " + \
             "[NOTE: Must be TIFF format]"
    )
    args = ap.parse_args()

    src = RJPEG(args.path)

    # Access all metadata items
    for key, value in src.metadata().items():
        print(f"{key}: {value}")

    # Access a single metadata item
    print(f"ImageWidth: {src.metadata('ImageWidth')}")

    # Report back the size and type of the embedded raw image
    shape = src.shape
    if shape is not None:
        rows, cols = shape
        size = src.size
        dtype = src.dtype
    else:
        rows, cols = None, None
        size = None
        dtype = None
    print(f"{cols} x {rows} [{size}] ({dtype})")

    # Write raw counts to file (uint16)
    if args.rawpath:
        print(f"Writing raw counts to {args.rawpath}")
        src.write_raw_counts(args.rawpath)

    # Write radiance to file (float32)
    if args.radpath:
        print(f"Writing radiance to {args.radpath}")
        src.write_radiance(args.radpath)

    # Write RGB to file (uint8)
    if args.rgbpath:
        print(f"Writing RGB to {args.rgbpath}")
        src.write_rgb(args.rgbpath)
