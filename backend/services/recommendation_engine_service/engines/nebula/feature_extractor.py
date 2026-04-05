import cv2
import numpy as np
from typing import Dict
import os


class CinematographicFeatureExtractor:
    """
    Week 1: The Eyes & Ears
    Extracts raw signals from video: Shot Boundaries, Color Palettes, and Motion Pacing.
    """

    def __init__(self, sample_rate: int = 24):
        self.sample_rate = sample_rate  # Process every Nth frame for speed

    def extract_features(self, video_path: str) -> Dict[str, np.ndarray]:
        """
        Extracts features from a video file.
        Returns a dictionary of raw feature arrays.
        """
        if not os.path.exists(video_path):
            print(
                f"Warning: Video path {video_path} not found. Returning mock features."
            )
            return self.get_mock_features()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        shot_changes = []
        color_histograms = []
        motion_vectors = []

        prev_frame = None
        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % self.sample_rate == 0:
                # 1. Color Histogram (RGB)
                hist = self._get_color_histogram(frame)
                color_histograms.append(hist)

                # 2. Shot Boundary Detection & Motion
                if prev_frame is not None:
                    diff = cv2.absdiff(frame, prev_frame)
                    mean_diff = np.mean(diff)
                    shot_changes.append(mean_diff)

                    # Simple motion complexity proxy
                    motion_vectors.append(mean_diff)

                prev_frame = frame.copy()

            frame_count += 1

        cap.release()

        return {
            "color_histograms": np.array(color_histograms),
            "shot_boundaries": np.array(shot_changes),
            "motion_complexity": np.array(motion_vectors),
        }

    def _get_color_histogram(self, frame: np.ndarray) -> np.ndarray:
        """Extracts a normalized 3D color histogram."""
        # Resize for speed
        small_frame = cv2.resize(frame, (64, 64))
        # 8 bins per channel = 512 features
        hist = cv2.calcHist(
            [small_frame], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256]
        )
        cv2.normalize(hist, hist)
        return hist.flatten()

    def get_mock_features(self, duration_steps: int = 100) -> Dict[str, np.ndarray]:
        """Generates synthetic features for testing the pipeline."""
        return {
            "color_histograms": np.random.rand(duration_steps, 512).astype(np.float32),
            "shot_boundaries": np.random.rand(duration_steps).astype(np.float32),
            "motion_complexity": np.random.rand(duration_steps).astype(np.float32),
        }


if __name__ == "__main__":
    extractor = CinematographicFeatureExtractor()
    features = extractor.get_mock_features()
    print(f"Extracted {len(features['color_histograms'])} frames of color histograms.")
    print(f"Motion vector shape: {features['motion_complexity'].shape}")
