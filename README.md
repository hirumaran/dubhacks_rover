# dubhacks_rover

**Run the end-to-end demo:** see [DEMO.md](DEMO.md) (rover finds an item, HuskyFind reports the match).

The standalone indoor rover showcase on branch **sarath** is in [`simulation-indoors/`](simulation-indoors/README.md). It captures all four directions every five simulation seconds and labels visible items. Open `simulation-indoors/Start Showcase.command` to run it.

The complete autonomous campus rover simulation is in [`simulation/`](simulation/).

- [Gates atrium indoor showcase](simulation/indoor_showcase/README.md) — autonomous indoor patrol, 360° camera and photo gallery
- [Setup and documentation](simulation/README.md)
- [Webots world](simulation/worlds/uw_autonomous.wbt)
- [Validation results](simulation/VALIDATION.md)

Item recognition runs on Perceptron Mk1.5 through Supabase Edge Functions
([`edge-functions/`](edge-functions/README.md)): they identify items in rover
photos, list them as found, help students fill in missing-item reports, and rate
whether a lost and a found item are the same object. The rover feeds them through
[`simulation/perception_bridge/`](simulation/perception_bridge/README.md), which
sends only camera images and the rover's GPS/compass pose.

The student app (HuskyFind, Expo/React Native) is in [`ui/`](ui/README.md). It reads the same
Supabase project: found listings, matches, missing reports and claims.

On macOS, open `simulation/Start Rover.command` to launch the rover (set
`PERCEPTION_INBOX` first to enable the perception bridge), or open
`simulation/worlds/uw_autonomous.wbt` in Webots R2025a or newer.
