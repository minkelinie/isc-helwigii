import cv2
import numpy as np
from pathlib import Path
import os

img_path = Path("/data/mijn_scherf.jpg")
img = cv2.imread(str(img_path))
print("Image shape:", img.shape if img is not None else "FAILED TO LOAD")

if img is not None:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=8)
    print("Connected components:", num_labels)
    print("File exists:", os.path.exists("/data/mijn_scherf.jpg"))