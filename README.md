# flir

A class definition for reading FLIR's proprietary radiometric JPEG (R-JPEG) file format.

A R-JPEG file (```*_LWIR_R.jpg```) contains an embedded raw thermal count image (uint16) and FLIR's provided radiometric conversion coefficients.  Depending on the camera model, the file (```*_MSX_R.jpg```) may also contain an embedded visible (RGB) image.

Instantiated objects will contain the raw thermal count image, the visible (RGB) image if present, and a radiance image computed using either the built-in FLIR coefficients -OR- using custom derived, pixel-by-pixel, gain/bias coefficient data.

&nbsp;
## Requirements

Python 3.9 or later

Non-standard Python modules required include
```
numpy
Pillow
```

If PIL is not available
```
pip install Pillow
```


&nbsp;
## Contact

**Carl Salvaggio, Ph.D.**  
Email: carl.salvaggio@rit.edu

Chester F. Carlson Center for Imaging Science  
Rochester Institute of Technology  
Rochester, New York 14623  
United States