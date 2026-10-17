# Campus Scout — autonomous UW campus rover in Webots

This is a native **Webots R2025a** project, with a physical six-wheel rover and actual OpenStreetMap building footprints and pedestrian paths around the University of Washington's Quad in Seattle.

## Indoor Gates atrium showcase

The new **[Gates atrium indoor showcase](indoor_showcase/README.md)** includes an approximate reference-inspired interior, autonomous lost-item search, orbit/follow cameras, a flash and a live photo gallery. Launch `indoor_showcase/Start Showcase.command` and open http://127.0.0.1:8768/. The original outdoor UW simulation below remains available.

## Run on this Mac

1. Double-click **Start Rover.command**, or open **worlds/uw_autonomous.wbt** in Webots and press Play.
2. The rover starts its autonomous patrol immediately. The main view follows the rover; the camera inset shows a simulated sensor feed.
3. Use Webots' Fast mode to accelerate the approximately 115-meter patrol. A real-time lap takes about 7–9 minutes including stops and turns. Timing depends on your computer and the obstacle detour.
4. Double-click **Start Gallery.command** and open **http://127.0.0.1:8767** to see captured items. It refreshes every three seconds. Ctrl+C in that launcher terminal stops the gallery server.

Python 3 is required. Controllers use only Python's standard library plus the controller API provided by Webots. The map-build dependencies are not needed to run the saved world. The active world has local textures and no remote PROTO dependencies.

## What runs autonomously

- **Global route:** A* planning on the OpenStreetMap pedestrian graph, through selected Quad checkpoints. Stairs, indoor corridors, private/no-access paths and pedestrian-area outlines are excluded from the route graph.
- **Localization:** simulated GPS and compass. The rover has an inertial unit and wheel encoders as well. It is not a Supervisor and cannot look up item world positions.
- **Drive:** six independently powered wheel joints, friction, mass, gravity and collision geometry. Skid steering is used; the suspension is rigid in this version.
- **Obstacle response:** a 360-degree lidar measures clearance. The local planner estimates temporary detour waypoints from those measurements, then rejoins the mapped route. A small obstacle placed in the route exercises this behavior. A 45-second blocked-detour timeout stops the robot rather than continuing indefinitely.
- **Search:** four approximately 94-degree RGB cameras cover the surroundings from the raised mast. Candidates must remain visible over several updates before the rover stops for a photograph.
- **Recognition:** Webots' built-in camera Recognition API supplies visible object categories and bounding boxes for tagged simulated props. This respects camera visibility and occlusion, but **is simulator ground truth, not a trained AI classifier**. It is isolated in `CampusRover.visible()` so a real detector can replace it.
- **Capture:** the rover stops, takes a tight crop of the actual camera image and writes a PNG and a location-free record. Five props include two backpacks, two books and a bottle.
- **Mission monitor:** a separate Supervisor displays status, saves verification images and ends bounded test runs. It does not drive or teleport the rover.

## Data separation

`gallery/items.json` contains only sample ID, item category, simulation time, image path and detector description. Images are tightly cropped sensor images with no embedded GPS metadata. The gallery server exposes **only** the gallery folder on loopback, not the map or logs. This project does not upload camera images to the earlier hosted browser demo or to a public student website.

Navigation maps, route geometry and private position telemetry are stored separately under `maps/` and `logs/`. Their coordinates are needed for simulation and debugging and are never included in the gallery records.

Captures persist across runs to avoid duplicate listings. To begin with an empty gallery while preserving previous evidence, run `python3 tools/archive_captures.py` before restarting Webots. It moves prior captures into `logs/capture_archives/` and resets the gallery manifest. Webots Reset alone restarts the robot but retains the gallery.

## Map source and fidelity

- **Source:** [OpenStreetMap](https://www.openstreetmap.org/#map=17/47.6578/-122.3067), downloaded October 17, 2026.
- **Attribution:** © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright).
- **Raw map:** `maps/uw_campus.osm`; download URL, bounding box and projection details are recorded in `maps/provenance.json`.
- **Official import:** `worlds/uw_imported.wbt` is the output of Webots' official OSM importer. It contains the larger downloaded area and may require Webots' remote assets if opened directly.
- **Runnable world:** `worlds/uw_autonomous.wbt` converts the selected importer output into self-contained native geometry: mapped road surfaces, nine building footprints and 53 tree positions. Procedural facades and canopies are approximations. It is not a photographic scan of UW.
- **Limitations:** terrain is flat, building heights/materials are approximate, people and traffic are not simulated, and OSM accessibility tags can be incomplete. This is a robotics development environment, not a validated model for outdoor deployment.

## Project structure

- `worlds/uw_autonomous.wbt` — complete runnable simulation.
- `protos/CampusScout.proto` — 203.2 × 203.2 mm six-wheel robot and sensors.
- `controllers/campus_rover/campus_rover.py` — autonomous controller and detector adapter.
- `controllers/mission_supervisor/mission_supervisor.py` — HUD and test monitor.
- `maps/mission.json` — map-derived route, rover geometry constants and planner metadata.
- `maps/pedestrian_graph.json` — pedestrian navigation graph.
- `gallery/` — local captured-item gallery.
- `logs/` — runtime telemetry and new test results (Git-ignored).
- `validation/` — reference run, rendered previews and five sample captures.
- `tools/build_project.py` / `tools/native_osm.py` — reproducible world and route generation from the saved import.

## Rebuild or extend

To regenerate from the saved OSM import, install `pyproj`, `shapely`, `numpy`, and `Pillow` into a virtual environment, then run `python tools/build_project.py`. To rerun the official importer from the raw map, also install `lxml` and `webcolors`, then use Webots' `Contents/Resources/osm_importer/importer.py` with the included `maps/importer_config.ini`. The importer refuses to overwrite an existing output, so choose a new output path.

To replace synthetic recognition with computer vision, implement a detector that returns category and image bounding box from each camera image inside `visible()`. Preserve multi-frame confirmation and the cropped-photo output. A pretrained detector must be validated against the rendered props; the current synthetic models are not guaranteed to resemble real training images.

## Bounded verification run

From this project folder on macOS:

```sh
CAMPUS_SCOUT_TEST_SECONDS=500 /Applications/Webots.app/Contents/MacOS/webots --batch --mode=fast --stdout --stderr worlds/uw_autonomous.wbt
```

The monitor writes `logs/test_result.json` and exits that Webots process when the time limit is reached. Ordinary runs omit the environment variable and continue patrolling. The passing reference run is preserved in `validation/`; new bounded runs write `logs/`.
