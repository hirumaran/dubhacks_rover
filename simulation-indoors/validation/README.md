# Larger indoor rover

`rover_size_revision.json` records the 0.70 × 0.60 m chassis patrol test and roof-edge camera checks. The rover completed a full lap in the 230-second bounded test, traveling 88.7 m without a detour or stop. Its cameras retain the 0.90 m optical height with calibrated mounting offsets and no extended arm. Earlier item-count results below belong to prior geometry.

# Actual Perceptron verification

`perception_verification.json` records the current targeted tests using the actual hosted model, including blank/empty-room negatives, imported backpack/laptop positives, physical two-view backpack confirmation and the earlier Supabase demo write. Cloud deployment was left unchanged; the local Vision Demo forces dry run. No simulator instance labels enter the actual vision pipeline. The older reference-mode reports below cover a different six-item scene and do not measure current model accuracy.

# Earlier reference-mode five-second snapshot workflow

Verified in native Webots R2025a on October 17, 2026. The new 230.02-second bounded run saved **46 snapshots** at targets 5, 10, 15…230 simulation seconds, with maximum timing error **0.056 s** (one 64 ms controller tick). It saved **15 empty snapshots**, captured multiple distinct objects in **4 snapshots**, identified **all six unique item IDs**, and completed **one full patrol lap**. The robot continued navigating while the timer captured; object detection never triggered a capture.

`periodic_result.json` holds the current behavioral result. `periodic_snapshots.json` contains all snapshot records and normalized pixel boxes. `periodic_snapshot_example.png` is the actual four-camera RGB mosaic from the 15-second scan, which found two items. `periodic_run.log` is the native controller log. The Supervisor's final packet can trail the file manifest by one controller update, so the manifest is authoritative for the terminal snapshot count.

The mosaic covers horizontal 360° using synchronized front/right/rear/left perspective views. Identification is Webots camera Recognition ground truth plus a description catalog keyed by simulated instance ID. It is not image-only AI recognition. Pixel boxes and relative camera direction do not expose building coordinates.

---

## Earlier object-triggered version (historical evidence)

Tested in native Webots R2025a on macOS, October 17, 2026.

The bounded run in `test_result.json` lasted **245.06 simulated seconds**. The physical rover completed **one full 77.786 m patrol lap**, traveled **88.61 m** including the next lap, and captured **all six items**: three backpacks, two books and a bottle. The sixth item was photographed at **188.99 s**. All three presentation camera modes were exercised using the webpage controls. No physical detours were needed on the clear prepared route.

`captures/` contains six actual cropped RGB sensor images. `items.json` is the corresponding public, location-free gallery manifest. `run.log` retains controller output. No item coordinates are passed to the detector; camera Recognition is Webots simulator ground truth. Indoor localization is idealized pose via simulated GPS/compass.

A subsequent 55-second camera-only check, using the same navigation and geometry, verified the closer orbit and unobstructed browser view. It intentionally ends before a full lap and records the first two discoveries. This short run does not replace the full-patrol result above.

The local server was checked for asset delivery, valid/invalid camera commands, cross-origin command rejection and private-log isolation. The webpage Restart mission control was verified to reload the world, restart both controllers, clear the manifest and capture the first backpack again. Native physical patrol and camera checks are behavioral validation, not evidence of real-world backpack-recognition accuracy or a measured reconstruction of the building.
