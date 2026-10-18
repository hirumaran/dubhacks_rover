# Validation on this Mac

Webots R2025a, Apple Silicon macOS. Full native simulation test, October 17, 2026.

- Simulated duration: **500.03 seconds**.
- Travel measured from simulated GPS: **152.65 meters**.
- Completed patrol laps: **1** (115.35 m planned loop plus detours and continuation into the next lap).
- Captured all **5/5** tagged sample items: two backpacks, two books and one bottle.
- Lidar local detour triggered and completed on both encounters with the route obstacle.
- Robot was still in PATROL state when the bounded test ended.
- No world parse errors or controller exceptions in the passing run.
- Gallery records were checked against an allowlist of non-location fields. Saved PNGs contain image-only IHDR/IDAT/IEND chunks, with no GPS/EXIF metadata.

Evidence: `validation/test_result.json`, `validation/validation.log`, `validation/capture_archives/`, `validation/campus_overview.png` and `validation/rover_preview.png`.

The verification uses simulated object-recognition labels, not a trained object detector. It validates this scene and the demonstrated obstacle, not arbitrary campus navigation or real-world object classification.
