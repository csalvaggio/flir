import json
import os
import shutil
import subprocess

import numpy as np

import io
import PIL
import PIL.Image


class RJPEG(object):

    def __init__(self, path: str, use_embedded_radiance: bool=False):
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

        self._path = path
        self._metadata = RJPEG._read_metadata(path)
        self._raw_counts = RJPEG._extract_embedded_raw_thermal_image(path)

        if use_embedded_radiance:
            self._compute_radiance_using_embedded_flir_approach()
        else:
            self._radiance = None

    @staticmethod
    def _read_metadata(path: str):
        cmd = ["exiftool", "-j", "-n", path]
        result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True)
        metadata = json.loads(result.stdout)[0]
        return metadata

    def metadata(self, key: str=None):
        if key is None:
            return self._metadata
        try:
            return self._metadata[key]
        except KeyError:
            msg = f"Provided key not found in metadata: {key}"
            raise KeyError(msg) from None

    @staticmethod
    def _extract_embedded_raw_thermal_image(path: str):
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

    def raw_counts(self):
        return self._raw_counts

    def write_raw_counts_to_tiff(self, path: str):
        PIL.Image.fromarray(self._raw_counts).save(path)

    def _compute_radiance_using_embedded_flir_approach(self):
        """
          Compute sensor-reaching radiance from raw counts according to

                            R1
              L = ---------------------- - F
                   R2 * (raw_count + O)

        """
        R1 = self._metadata["PlanckR1"]
        R2 = self._metadata["PlanckR2"]
        O  = self._metadata["PlanckO"]
        F  = self._metadata["PlanckF"]
        B =  self._metadata["PlanckB"]

        raw_counts = (2**16 - 1) - self._raw_counts

        denominator = (R2 * (raw_counts + O)).astype(np.float32)
        bad_pixels = denominator <= 0
        denominator[bad_pixels] = np.nan
        self._radiance = (R1 / denominator - F).astype(np.float32)

    def radiance(self):
        return self._radiance

    def write_radiance_to_tiff(self, path: str):
        PIL.Image.fromarray(self._radiance, mode="F").save(path)



if __name__ == '__main__':

    import argparse
    import flir

    description = "Test harness to read in and create a FLIR RJPEG object"
    ap = argparse.ArgumentParser(description=description)
    help_msg = "path to a FLIR radiometric JPEG"
    ap.add_argument("path", help=help_msg)
    help_msg = "use embedded FLIR radiance approach [default is False]"
    ap.add_argument("-e", "--use_embedded_radiance",
                    action="store_true", default=False, help=help_msg)
    help_msg = "output path to TIFF to store raw counts (uint16)"
    ap.add_argument("-r", "--rawpath", default=None, help=help_msg)
    help_msg = "output path to TIFF to store radiance (float32)"
    ap.add_argument("-l", "--radpath", default=None, help=help_msg)
    args = ap.parse_args()

    src = flir.RJPEG(args.path,
                     use_embedded_radiance=args.use_embedded_radiance)

    # Access all metadata items
    for key, value in src.metadata().items():
        print(f"{key}: {value}")

    # Access a single metadata item
    print(f"ImageWidth: {src.metadata("ImageWidth")}")

    # Report back the size and type of the embedded raw image
    cols = src.raw_counts().shape[1]
    rows = src.raw_counts().shape[0]
    dtype = src.raw_counts().dtype
    print(f"{cols} x {rows} ({dtype})")

    # Write raw counts to TIFF (uint16)
    if args.rawpath:
        print(f"Writing raw counts to {args.rawpath}")
        src.write_raw_counts_to_tiff(args.rawpath)

    # Write radiance to TIFF (float32)
    if args.radpath:
        if src.radiance() is None:
            print(f"RJPEG object contains no radiance, ignoring write request")
        else:
            print(f"Writing radiance to {args.radpath}")
            src.write_radiance_to_tiff(args.radpath)
