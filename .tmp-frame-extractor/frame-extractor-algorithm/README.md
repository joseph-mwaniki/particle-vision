# Gaussian Splat Frame Selector

A local-first FastAPI app that uploads a walkthrough video, analyzes frames for blur, exposure problems, redundancy, and temporal coverage, then exports a curated set of frames for use in COLMAP preprocessing.

## Features

- Upload videos from the browser
- Extract video metadata and analyze frames in the backend
- Detect blur using variance of the Laplacian
- Detect unrealistic exposure conditions
- Filter near-duplicate frames by normalized visual difference
- Protect temporal coverage with configurable windowing and minimum-frame rules
- Export selected frames, metadata JSON, and CSV
- Prepare a COLMAP-ready input folder

## Quick start

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Start the app:

   ```bash
   uvicorn backend.main:app --reload
   ```

3. Open the browser to http://localhost:8000

## Notes

This is a deterministic preprocessing pipeline built primarily with OpenCV and NumPy. It does not use machine learning models.
