# Campus Scout — Gates atrium showcase

A native Webots indoor simulation with a physical **203.2 × 203.2 mm (8 × 8 inch)** six-wheel rover, autonomous ground-floor patrol, 360° orbit/follow cameras, and a local snapshot-and-item presentation gallery. A synchronized 360° capture runs every five simulation seconds, regardless of detections.

The interior is **an approximate interpretation of the supplied Gates atrium photo and floor-plan screenshot**, not a surveyed digital twin. It echoes the stacked glass balconies, steel-and-oak stairs, cyan skylight, timber frontage, gray tile, purple seating and adjoining corridor wings. The original reference images are not embedded or published. The rover remains on the ground floor; it does not climb the stairs or operate elevators.

## Launch

1. Install **Webots R2025a** and Python 3.10+ (already available on the development Mac).
2. Double-click **Start Showcase.command**. This starts Webots in real time and the local presentation server. Each launcher run archives old captures locally and starts a fresh mission. Opening/reloading the native world also starts fresh snapshot and item manifests, with prior records archived under `logs/session_history/`.
3. Open **http://127.0.0.1:8768/**. Use **360° orbit**, **Follow rover**, or **Atrium view**. **Restart mission** reloads the native world and both controllers, and clears its gallery manifest; previous image files remain on disk.
4. Let the scout explore. Every five simulation seconds it flashes its mast LED and saves all four RGB camera views as one 360° horizontal snapshot, including empty scenes. It then identifies every recognizable item in those sampled frames, draws labeled boxes in the snapshot viewer, and saves individual crops. It keeps patrolling; seeing an item never triggers an extra photograph. The webpage also plays a white shutter flash and a brief “adding” animation.
5. Ctrl+C in the launcher terminal stops the processes it launched.

The saved `.wbt`, textures, PROTO and Python controllers are self-contained. No downloaded assets or extra Python packages are required to run. To use Webots directly, open `worlds/gates_atrium.wbt`, press Play, and run **Start Presentation.command** separately. If the world is opened without the launcher, the native camera overlays may default to visible; copy `tools/showcase.wbproj` to `worlds/.gates_atrium.wbproj` before opening to use the prepared view. Set `GATES_NATIVE_PHOTO=1` before launching Webots to draw the optional native `photo_board` Display. The default uses the browser gallery for photos to leave the native scene unobstructed.

## Autonomy and photography

- **Navigation:** 77.786 m loop through an approximate atrium and corridor, 158 short waypoints, physical skid steering, six wheel motors and collision geometry. A lap takes roughly three and a half simulation minutes, with no object-triggered inspection stops. Speed is 0.4 m/s.
- **Localization:** idealized simulated indoor pose from Webots GPS/compass, plus inertial tilt monitoring and wheel encoders. Real indoor deployment would need a localization system such as SLAM; this is not a claim that GPS works inside the actual building.
- **Obstacle response:** a 360° lidar checks clearance and can construct a local detour. A blocked timeout stops the rover. The prepared clear indoor patrol does not require detours.
- **Discovery:** four 640 × 480 RGB cameras with Webots Recognition. Only scheduled snapshots are analyzed. Recognition covers visible tagged props within the cameras’ 3 m recognition range, subject to occlusion and minimum image-size checks. Adjacent-camera duplicates are consolidated by exact item ID; repeat sightings update the same listing. Six props include three backpacks, two books and a bottle. Camera occlusion and field of view matter.
- **Recognition is simulator ground truth**, not a trained backpack detector. The `snapshot()` recognition block in the rover controller is the replacement point for an actual detector. `maps/items.json` supplies descriptions for exact simulated IDs (for example, rust-colored backpack GATES-001); it contains no object positions. The rover controller is a normal Robot and never reads item world coordinates or teleports itself.
- **Cinematography:** a separate Supervisor tracks the rover only to move the viewing camera, draw presentation content and relay status. Its true-pose access is not passed to the navigation controller.
- **Snapshots:** synchronized 640 × 480 front/right/rear/left buffers form a 2560 × 480 four-view PNG, covering the full horizontal 360°. This is an explicitly labeled perspective mosaic, not a stitched spherical panorama. Capture times target 5, 10, 15… simulation seconds, quantized to the 64 ms controller tick.
- **Identification:** every snapshot retains all visible recognized instances, including already-seen items. Labels include description, exact simulated ID and relative camera direction. Pixel bounding boxes refer only to the image, not building positions. Individual RGB crops update a deduplicated gallery. Empty snapshots are saved and shown. Public data has **no map/GPS coordinates**.
- **Review:** click any timestamp to hold a historical scan; use **Return to latest scan** to resume live snapshots. Restart clears both snapshot and item manifests.

“Adding to gallery” is presentation choreography. Files are stored locally; nothing is uploaded to the earlier hosted site or a remote student website. The server binds to loopback only and serves `presentation/`, not navigation logs. The external orbit camera is separate from the actual four-camera snapshot rig. The snapshot viewer shows the rover’s sensor images with their detection boxes. Five seconds refers to simulation time, so accelerated Webots playback accelerates the timer too.

## Files

- `worlds/gates_atrium.wbt` and `worlds/textures/`: complete indoor environment.
- `protos/IndoorScout.proto`: rover, physical wheels, sensors and flash LED.
- `controllers/indoor_rover/`: sensor-driven patrol, detection and camera capture.
- `controllers/showcase_director/`: orbit/follow/overview camera, telemetry, native photo Display and optional render recording.
- `presentation/`: responsive local showcase and live photo gallery.
- `tools/serve_showcase.py`: loopback server and validated camera/reset commands.
- `tools/launch_showcase.py`: portable launcher (macOS path or `webots` on PATH).
- `maps/mission.json`: approximate-layout patrol; it is not the actual building's measured floor plan.
- `validation/`: verified run report, log and six example sensor crops.

Runtime images, local settings, recordings and navigation logs are ignored by Git. A freshly cloned project starts its gallery when launched.

## Rebuild / record

The saved world runs without build dependencies. To regenerate its procedural geometry/textures, install Pillow and run `python3 tools/build_atrium.py` from this project. The generator reuses the outdoor project's rover PROTO at `../protos/CampusScout.proto`; it does not download assets.

For a bounded verification and frame sequence:

```sh
GATES_TEST_SECONDS=245 GATES_RECORD=1 /Applications/Webots.app/Contents/MacOS/webots \
  --batch --mode=fast --stdout --stderr --port=1242 worlds/gates_atrium.wbt
```

Use a fresh gallery for new capture validation. `GATES_RECORD=1` exports native rendered frames every 0.128 simulated seconds to `recordings/frames/`. Convert them with FFmpeg at `-framerate 7.8125`; this preserves simulation timing. Camera rendering can be slower than real time on some machines. Ordinary runs do not retain frame sequences.
