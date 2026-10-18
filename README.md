# dubhacks_rover

The standalone indoor rover showcase on branch **sarath** is in [`simulation-indoors/`](simulation-indoors/README.md). It captures all four directions every five simulation seconds and labels visible items. Open `simulation-indoors/Start Showcase.command` to run it.

The complete autonomous campus rover simulation is in [`simulation/`](simulation/).

- [Gates atrium indoor showcase](simulation/indoor_showcase/README.md) — autonomous indoor patrol, 360° camera and photo gallery
- [Setup and documentation](simulation/README.md)
- [Webots world](simulation/worlds/uw_autonomous.wbt)
- [Validation results](simulation/VALIDATION.md)

The on-rover intelligence layer ([`perception/`](perception/)) runs
Isaac-0.2-1B locally: camera frames -> detections -> stable object IDs ->
geotags -> Supabase `sightings`. Desk QR codes (`perception/kiosk/qr/`) open a
phone form; cloud dispatch sends the report to the closest live rover. See
[perception/README.md](perception/README.md) and
[perception/QR_AND_FLEET.md](perception/QR_AND_FLEET.md).

On macOS, open `simulation/Start Rover.command` to launch the rover (set
`PERCEPTION_INBOX` first to enable the perception bridge), or open
`simulation/worlds/uw_autonomous.wbt` in Webots R2025a or newer.
