# Verified indoor patrol

Tested in native Webots R2025a on macOS, October 17, 2026.

The bounded run in `test_result.json` lasted **245.06 simulated seconds**. The physical rover completed **one full 77.786 m patrol lap**, traveled **88.61 m** including the next lap, and captured **all six items**: three backpacks, two books and a bottle. The sixth item was photographed at **188.99 s**. All three presentation camera modes were exercised using the webpage controls. No physical detours were needed on the clear prepared route.

`captures/` contains six actual cropped RGB sensor images. `items.json` is the corresponding public, location-free gallery manifest. `run.log` retains controller output. No item coordinates are passed to the detector; camera Recognition is Webots simulator ground truth. Indoor localization is idealized pose via simulated GPS/compass.

A subsequent 55-second camera-only check, using the same navigation and geometry, verified the closer orbit and unobstructed browser view. It intentionally ends before a full lap and records the first two discoveries. This short run does not replace the full-patrol result above.

The local server was checked for asset delivery, valid/invalid camera commands, cross-origin command rejection and private-log isolation. The webpage Restart mission control was verified to reload the world, restart both controllers, clear the manifest and capture the first backpack again. Native physical patrol and camera checks are behavioral validation, not evidence of real-world backpack-recognition accuracy or a measured reconstruction of the building.
