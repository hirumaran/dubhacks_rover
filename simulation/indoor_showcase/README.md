# Campus Scout — Gates atrium showcase

A native Webots indoor simulation with a physical **203.2 × 203.2 mm (8 × 8 inch)** six-wheel rover, autonomous ground-floor patrol, 360° orbit/follow cameras, and a local photo presentation gallery.

The interior is **an approximate interpretation of the supplied Gates atrium photo and floor-plan screenshot**, not a surveyed digital twin. It echoes the stacked glass balconies, steel-and-oak stairs, cyan skylight, timber frontage, gray tile, purple seating and adjoining corridor wings. The original reference images are not embedded or published. The rover remains on the ground floor; it does not climb the stairs or operate elevators.

## Launch

1. Install **Webots R2025a** and Python 3.10+ (already available on the development Mac).
2. Double-click **Start Showcase.command**. This starts Webots in real time and the local presentation server. Each launcher run archives old captures locally and starts a fresh mission.
3. Open **http://127.0.0.1:8768/**. Use **360° orbit**, **Follow rover**, or **Atrium view**. **Restart mission** reloads the native world and both controllers, and clears its gallery manifest; previous image files remain on disk.
4. Let the scout explore. It stops at a visible item, flashes its mast LED, saves a real camera crop, then adds the image to the presentation gallery. The webpage also plays a white shutter flash and a brief “adding” animation.
5. Ctrl+C in the launcher terminal stops the processes it launched.

The saved `.wbt`, textures, PROTO and Python controllers are self-contained. No downloaded assets or extra Python packages are required to run. To use Webots directly, open `worlds/gates_atrium.wbt`, press Play, and run **Start Presentation.command** separately. If the world is opened without the launcher, the native camera overlays may default to visible; copy `tools/showcase.wbproj` to `worlds/.gates_atrium.wbproj` before opening to use the prepared view. Set `GATES_NATIVE_PHOTO=1` before launching Webots to draw the optional native `photo_board` Display. The default uses the browser gallery for photos to leave the native scene unobstructed.

## Autonomy and photography

- **Navigation:** 77.786 m loop through an approximate atrium and corridor, 158 short waypoints, physical skid steering, six wheel motors and collision geometry. A roughly four-minute lap includes inspection stops. Speed is 0.4 m/s.
- **Localization:** idealized simulated indoor pose from Webots GPS/compass, plus inertial tilt monitoring and wheel encoders. Real indoor deployment would need a localization system such as SLAM; this is not a claim that GPS works inside the actual building.
- **Obstacle response:** a 360° lidar checks clearance and can construct a local detour. A blocked timeout stops the rover. The prepared clear indoor patrol does not require detours.
- **Discovery:** four 640 × 480 RGB cameras with Webots Recognition. Candidates must be visible within 1.25 m for several updates; the rover stops and inspects them before capture. Six props include three backpacks, two books and a bottle. Camera occlusion and field of view matter.
- **Recognition is simulator ground truth**, not a trained backpack detector. The `visible()` adapter in the rover controller is the replacement point for an actual detector. The rover controller is a normal Robot and never reads item world coordinates or teleports itself.
- **Cinematography:** a separate Supervisor tracks the rover only to move the viewing camera, draw presentation content and relay status. Its true-pose access is not passed to the navigation controller.
- **Photographs:** tightly cropped PNGs come from the actual RGB sensor buffer. Public gallery records contain category, ID, simulation time, image path and detector description, with **no item coordinates**.

“Adding to gallery” is presentation choreography. Files are stored locally; nothing is uploaded to the earlier hosted site or a remote student website. The server binds to loopback only and serves `presentation/`, not navigation logs. The 360° view is an orbiting external camera; the sensing rig uses four overlapping cameras rather than a stitched panoramic image.

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
